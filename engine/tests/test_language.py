import random
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import pymupdf
import pytest

from samples_markup import ARABIC, has_joined_forms, normal, run

ENGINE_ROOT = Path(__file__).resolve().parent.parent

PAIRS = [
    ("The weather is nice today.", "الطقس جميل اليوم."),
    ("I would like to book a table for two.", "أود أن أحجز طاولة لشخصين."),
    ("The library opens at nine in the morning.", "تفتح المكتبة في التاسعة صباحا."),
    ("Students must bring their identity cards.", "يجب على الطلاب إحضار بطاقات الهوية الخاصة بهم."),
    ("Where is the nearest hospital?", "أين أقرب مستشفى؟"),
    ("The exam will be held next Sunday.", "سيعقد الامتحان يوم الأحد القادم."),
    ("Water boils at one hundred degrees Celsius.", "يغلي الماء عند مئة درجة مئوية."),
    ("My brother works as an engineer in a large company.", "يعمل أخي مهندسا في شركة كبيرة."),
    ("Please close the door when you leave.", "من فضلك أغلق الباب عندما تغادر."),
    ("Reading every day improves your vocabulary.", "القراءة كل يوم تحسن مفرداتك."),
    ("The train to the capital leaves at six.", "يغادر القطار المتجه إلى العاصمة في السادسة."),
    ("Education is the key to a better future.", "التعليم هو مفتاح مستقبل أفضل."),
]


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub("[\u064b-\u065f\u0670\u0640]", "", text)
    text = re.sub("[أإآٱ]", "ا", text).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"[^\w]", "", text)


def chrf(hypothesis: str, reference: str, max_n: int = 6, beta: float = 2.0) -> float:
    """Character n-gram F-score (chrF), 0 to 1, spaces and punctuation ignored."""
    hyp, ref = fold(hypothesis), fold(reference)
    precisions, recalls = [], []
    for n in range(1, max_n + 1):
        h = Counter(hyp[i:i + n] for i in range(len(hyp) - n + 1))
        r = Counter(ref[i:i + n] for i in range(len(ref) - n + 1))
        if not h or not r:
            continue
        overlap = sum((h & r).values())
        precisions.append(overlap / sum(h.values()))
        recalls.append(overlap / sum(r.values()))
    p, r = sum(precisions) / len(precisions), sum(recalls) / len(recalls)
    return 0.0 if p + r == 0 else (1 + beta ** 2) * p * r / (beta ** 2 * p + r)


def english_pdf(path: Path, with_image: bool = True) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(50, 50, 545, 130), color=None, fill=(0.85, 0.92, 1))
    page.insert_text((60, 90), "Welcome to the library", fontsize=24, color=(0, 0, 0.5))
    page.insert_textbox(pymupdf.Rect(60, 160, 535, 300), "The library opens at nine in the morning. Students can "
                        "borrow up to five books for two weeks. Please keep silence in the reading rooms.", fontsize=13)
    page.draw_line((60, 320), (535, 320), color=(1, 0, 0), width=2)
    if with_image:
        pix = pymupdf.Pixmap(pymupdf.csRGB, 80, 60, bytes([30, 160, 90]) * (80 * 60), False)
        page.insert_image(pymupdf.Rect(60, 400, 220, 520), pixmap=pix)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture(scope="module")
def translated(tmp_path_factory):
    folder = tmp_path_factory.mktemp("tr")
    src = english_pdf(folder / "en.pdf")
    reply = run("translate", {"file": str(src), "source": "en", "target": "ar"})
    return src, reply["outputs"][0]["path"], reply["summary"]


def test_translate_keeps_layout_images_and_graphics(translated):
    src, out, summary = translated
    with pymupdf.open(src) as before, pymupdf.open(out) as after:
        assert len(after[0].get_images()) == len(before[0].get_images()) == 1
        shapes_before = [d["rect"] for d in before[0].get_drawings()]
        shapes_after = [d["rect"] for d in after[0].get_drawings()]
        assert shapes_after == shapes_before, "background box and rule line must survive the text swap"
        words = after[0].get_text("words")
        blocks = [pymupdf.Rect(b[:4]) for b in before[0].get_text("blocks")]
    outside = [w for w in words if not any(pymupdf.Rect(w[:4]) in (b + (-6, -6, 6, 6)) for b in blocks)]
    assert not outside, f"translated words must stay inside the original text rectangles: {outside[:3]}"
    assert summary["blocks"] == 2


def test_translate_removes_the_original_text_and_writes_joined_arabic(translated):
    _, out, _ = translated
    with pymupdf.open(out) as doc:
        raw = doc[0].get_text()
    assert not re.search("[A-Za-z]{3,}", raw), raw
    assert has_joined_forms(raw)
    assert re.search("[\u0600-\u06ff]{3,}", normal(raw))
    assert "المكتبة" in normal(raw), "the word 'library' should come out as المكتبة"


def test_translate_image_pixels_are_untouched(translated):
    src, out, _ = translated
    def image_pixels(path):
        with pymupdf.open(path) as doc:
            pix = pymupdf.Pixmap(doc, doc[0].get_images()[0][0])
            return np.frombuffer(pix.samples, dtype=np.uint8)
    assert np.array_equal(image_pixels(src), image_pixels(out))


def test_translate_back_to_english_recovers_the_meaning(translated, tmp_path):
    src, out, _ = translated
    back = run("translate", {"file": out, "source": "ar", "target": "en", "out_dir": str(tmp_path)})
    with pymupdf.open(back["outputs"][0]["path"]) as doc:
        text = doc[0].get_text().lower()
    expected = {"library", "opens", "students", "borrow", "books", "weeks", "silence", "reading", "rooms", "welcome"}
    keep = {w for w in expected if w in text or (w == "silence" and "quiet" in text)}
    assert len(keep) / len(expected) >= 0.6, (len(keep), sorted(expected - keep))


def test_measured_translation_quality(tmp_path):
    """Numbers, not feelings: chrF on 12 simple sentences, both directions (see the report for the figures)."""
    from freepdf_engine.tools import _lang_engine as engine
    to_ar = engine.translate_sentences([e for e, _ in PAIRS], "en", "ar")
    to_en = engine.translate_sentences([a for _, a in PAIRS], "ar", "en")
    engine.release_models()
    score_ar = sum(chrf(h, r) for h, (_, r) in zip(to_ar, PAIRS)) / len(PAIRS)
    score_en = sum(chrf(h, r) for h, (r, _) in zip(to_en, PAIRS)) / len(PAIRS)
    exact_en = sum(fold(h) == fold(r) for h, (r, _) in zip(to_en, PAIRS))
    Path(tmp_path / "scores.txt").write_text(f"en->ar chrF {score_ar:.3f}; ar->en chrF {score_en:.3f}; exact {exact_en}/12")
    assert score_ar > 0.40, score_ar
    assert score_en > 0.45, score_en
    print(f"\nTRANSLATION chrF en->ar {score_ar:.3f}  ar->en {score_en:.3f}  exact ar->en {exact_en}/12")


def test_models_load_lazily_and_nothing_lands_in_the_user_profile():
    code = ("import sys, freepdf_engine.tools.language; "
            "print('ctranslate2' in sys.modules, 'argostranslate' in sys.modules, 'torch' in sys.modules)")
    done = subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=ENGINE_ROOT, capture_output=True, timeout=60)
    assert done.stdout.decode().split()[-3:] == ["False", "False", "False"], done.stderr.decode()
    assert not (Path.home() / ".local" / "share" / "argos-translate").exists()


def test_translate_errors_are_clear(tmp_path):
    from freepdf_engine.core import ToolError
    src = english_pdf(tmp_path / "en.pdf", with_image=False)
    with pytest.raises(ToolError) as missing:
        run("translate", {"file": str(src), "source": "en", "target": "fr"})
    assert missing.value.code == "missing_resource"
    blank = tmp_path / "blank.pdf"
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(str(blank))
    with pytest.raises(ToolError) as empty:
        run("translate", {"file": str(blank), "source": "en", "target": "ar"})
    assert "Recognize text" in empty.value.message


def test_translate_arabic_page_to_english_places_text_in_the_same_rect(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_htmlbox(pymupdf.Rect(72, 80, 523, 160), "تفتح المكتبة في التاسعة صباحا. يمكن للطلاب استعارة خمسة كتب.",
                        css="@font-face{font-family:a;src:url(arial.ttf);}body{font-family:a;font-size:16pt;direction:rtl}",
                        archive=pymupdf.Archive(r"C:\Windows\Fonts"))
    src = tmp_path / "ar.pdf"
    doc.save(str(src))
    original = pymupdf.Rect(pymupdf.open(str(src))[0].get_text("blocks")[0][:4])
    out = run("translate", {"file": str(src), "source": "ar", "target": "en"})["outputs"][0]["path"]
    with pymupdf.open(out) as result:
        text = result[0].get_text().lower()
        box = pymupdf.Rect(result[0].get_text("blocks")[0][:4])
    assert "library" in text and "students" in text
    assert box in original + (-8, -8, 8, 8), (box, original)


ARTICLE_EN = [
    ("Solar power converts sunlight directly into electricity using photovoltaic panels.", 1),
    ("I had a sandwich for lunch while writing this report.", 0),
    ("A solar panel is made of many silicon cells that release electrons when sunlight hits them.", 1),
    ("The parking lot outside the office was full again this morning.", 0),
    ("The electricity produced by solar panels can power homes, schools and entire factories.", 1),
    ("Falling prices have made solar power one of the cheapest sources of electricity in many countries.", 1),
    ("My neighbour recently painted his fence bright green.", 0),
    ("Batteries store the extra solar energy so that homes can use electricity at night.", 1),
    ("The weather forecast for next week says it will rain on Tuesday.", 0),
    ("Governments support solar panels with tax credits that lower the cost for families.", 1),
    ("Our team meeting starts at three o'clock on Thursday.", 0),
    ("Critics note that solar power depends on sunlight and produces less electricity in winter.", 1),
    ("The cafeteria will serve soup tomorrow.", 0),
    ("Engineers keep improving panel efficiency so that each panel captures more sunlight.", 1),
    ("Someone left an umbrella in the lobby yesterday.", 0),
]
ARTICLE_AR = [
    ("تحول الطاقة الشمسية ضوء الشمس مباشرة إلى كهرباء باستخدام الألواح الكهروضوئية.", 1),
    ("تناولت شطيرة على الغداء أثناء كتابة هذا التقرير.", 0),
    ("يتكون اللوح الشمسي من خلايا السيليكون التي تطلق الإلكترونات عندما يسقط عليها ضوء الشمس.", 1),
    ("كان موقف السيارات أمام المكتب ممتلئا مرة أخرى هذا الصباح.", 0),
    ("يمكن للكهرباء التي تنتجها الألواح الشمسية أن تشغل المنازل والمدارس والمصانع الكبيرة.", 1),
    ("أدى انخفاض الأسعار إلى جعل الطاقة الشمسية من أرخص مصادر الكهرباء في كثير من الدول.", 1),
    ("قام جاري مؤخرا بدهان سور حديقته باللون الأخضر الفاتح.", 0),
    ("تخزن البطاريات فائض الطاقة الشمسية لكي تستخدم المنازل الكهرباء ليلا.", 1),
    ("تتوقع نشرة الطقس أن تمطر السماء يوم الثلاثاء من الأسبوع القادم.", 0),
    ("تدعم الحكومات الألواح الشمسية بإعفاءات ضريبية تخفض التكلفة على الأسر.", 1),
    ("يبدأ اجتماع فريقنا في الساعة الثالثة بعد ظهر يوم الخميس.", 0),
    ("يشير المنتقدون إلى أن الطاقة الشمسية تعتمد على ضوء الشمس وتنتج كهرباء أقل في الشتاء.", 1),
    ("ستقدم الكافتيريا الشوربة غدا اليوم.", 0),
    ("يواصل المهندسون تحسين كفاءة الألواح حتى يلتقط كل لوح مزيدا من ضوء الشمس.", 1),
    ("ترك شخص ما مظلة في بهو المبنى أمس.", 0),
]


def article_pdf(path: Path, sentences, arabic: bool) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    body = " ".join(s for s, _ in sentences)
    if arabic:
        page.insert_htmlbox(pymupdf.Rect(50, 60, 545, 780), body, archive=pymupdf.Archive(r"C:\Windows\Fonts"),
                            css="@font-face{font-family:a;src:url(arial.ttf);}body{font-family:a;font-size:12pt;direction:rtl}")
    else:
        page.insert_textbox(pymupdf.Rect(50, 60, 545, 780), body, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


def summary_stats(path, sentences, length):
    reply = run("summarize", {"file": str(path), "length": length})
    key = {fold(s) for s, flag in sentences if flag}
    chosen = [s for s, _ in sentences if fold(s) in fold(reply["summary"]["text"]) or
              fold(s)[:40] in fold(reply["summary"]["text"])]
    precision = sum(fold(s) in key for s in chosen) / max(len(chosen), 1)
    return reply, chosen, precision


@pytest.mark.parametrize("name,sentences,arabic", [("english", ARTICLE_EN, False), ("arabic", ARTICLE_AR, True)])
def test_summary_lengths_differ_and_pick_the_key_sentences(tmp_path, name, sentences, arabic):
    path = article_pdf(tmp_path / f"{name}.pdf", sentences, arabic)
    counts, precision = {}, {}
    for length in ("short", "medium", "long"):
        reply, chosen, precision[length] = summary_stats(path, sentences, length)
        counts[length] = reply["summary"]["sentences"]
        assert Path(reply["outputs"][0]["path"]).read_text(encoding="utf-8-sig").strip() == reply["summary"]["text"].strip()
    assert counts["short"] < counts["medium"] < counts["long"], counts
    words = {k: len(run("summarize", {"file": str(path), "length": k})["summary"]["text"].split()) for k in counts}
    assert words["short"] < words["medium"] < words["long"], words
    assert precision["short"] == 1.0 and precision["medium"] == 1.0, precision
    assert precision["long"] >= 0.8, precision
    print(f"\nSUMMARY {name}: sentences {counts} precision {precision}")


def test_summary_beats_random_and_lead_baselines_on_a_harder_article(tmp_path):
    """Relevant sentences are mixed through the text; measure how many the summary recovers versus chance."""
    sentences = ARTICLE_EN[1:] + ARTICLE_EN[:1]  # key sentence is last, so a 'lead' baseline cannot cheat
    path = article_pdf(tmp_path / "hard.pdf", sentences, False)
    key = {fold(s) for s, flag in sentences if flag}
    reply = run("summarize", {"file": str(path), "length": "medium"})
    picked = [s for s, _ in sentences if fold(s) in fold(reply["summary"]["text"])]
    precision = sum(fold(s) in key for s in picked) / len(picked)
    rng = random.Random(0)
    chance = np.mean([sum(fold(s) in key for s, _ in rng.sample(sentences, len(picked))) / len(picked)
                      for _ in range(300)])
    lead = sum(fold(s) in key for s, _ in sentences[:len(picked)]) / len(picked)
    assert precision > chance + 0.3 and precision > lead, (precision, chance, lead)
    print(f"\nSUMMARY precision {precision:.2f} vs random {chance:.2f} vs lead {lead:.2f}")


def test_arabic_sentence_splitting():
    from freepdf_engine.tools._lang_engine import split_sentences
    parts = split_sentences("ما هذا؟ هذا كتاب. هل تقرأ؟ نعم! قابلت د. أحمد في المكتبة. ثم ذهبنا.")
    assert parts == ["ما هذا؟", "هذا كتاب.", "هل تقرأ؟", "نعم!", "قابلت د. أحمد في المكتبة.", "ثم ذهبنا."]
    assert split_sentences("Dr. Smith met Mr. Jones. They left at 3.5 p.m. Then it rained.")[:2] == \
        ["Dr. Smith met Mr. Jones.", "They left at 3.5 p.m."]


def test_summary_handles_pages_scanned_files_and_bad_length(tmp_path):
    from freepdf_engine.core import ToolError
    doc = pymupdf.open()
    for sentences in (ARTICLE_EN[:8], ARTICLE_EN[8:]):
        doc.new_page(width=595, height=842).insert_textbox(
            pymupdf.Rect(50, 60, 545, 780), " ".join(s for s, _ in sentences), fontsize=12)
    path = tmp_path / "two.pdf"
    doc.save(str(path))
    first = run("summarize", {"file": str(path), "length": "short", "pages": "1"})["summary"]
    both = run("summarize", {"file": str(path), "length": "short"})["summary"]
    assert first["total_sentences"] < both["total_sentences"]
    blank = tmp_path / "blank.pdf"
    with pymupdf.open() as empty:
        empty.new_page()
        empty.save(str(blank))
    with pytest.raises(ToolError) as scanned:
        run("summarize", {"file": str(blank)})
    assert "Recognize text" in scanned.value.message
    with pytest.raises(ToolError) as bad:
        run("summarize", {"file": str(path), "length": "huge"})
    assert bad.value.code == "bad_args"
    assert ARABIC
