"""Security tools: protect (encrypt) and unlock (remove encryption)."""
import secrets

from ..core import Job, ToolError, output_path, require, require_file, result
from ..registry import tool
from ._pdf_common import has_encryption, open_pdf, pymupdf, save_pdf


def _permissions(args: dict) -> int:
    """PDF permission bits from allow_print, allow_copy and allow_modify (each defaults to allowed)."""
    bits = pymupdf.PDF_PERM_ACCESSIBILITY
    if args.get("allow_print", True):
        bits |= pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
    if args.get("allow_copy", True):
        bits |= pymupdf.PDF_PERM_COPY
    if args.get("allow_modify", True):
        bits |= pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ASSEMBLE | pymupdf.PDF_PERM_ANNOTATE | pymupdf.PDF_PERM_FORM
    return bits


@tool("protect")
def protect(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    new_password = str(require(args, "password"))
    restricted = not all(args.get(key, True) for key in ("allow_print", "allow_copy", "allow_modify"))
    # Restrictions only bind people who open the file with the user password, so the
    # owner password must differ from it. Nobody needs the owner password afterwards.
    owner_password = secrets.token_urlsafe(24) if restricted else new_password
    with open_pdf(src, args.get("current_password")) as doc:
        job.progress(0.3, "Encrypting")
        out_path = output_path(src, "protected", out_dir=args.get("out_dir"))
        save_pdf(
            doc, out_path,
            garbage=3,
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=new_password,
            owner_pw=owner_password,
            permissions=_permissions(args),
        )
    return result([out_path], encryption="AES-256", restricted=restricted)


@tool("unlock")
def unlock(job: Job, args: dict) -> dict:
    src = require_file(require(args, "file"))
    try:
        with pymupdf.open(str(src)) as probe:
            was_encrypted = bool(probe.is_pdf and has_encryption(probe))
            needed_password = bool(probe.is_pdf and probe.needs_pass)
    except Exception as err:
        raise ToolError("not_a_pdf", f"{src.name} is not a PDF, or it is damaged. Try Repair a PDF.") from err
    job.progress(0.3, "Removing protection")
    with open_pdf(src, args.get("password")) as doc:
        out_path = output_path(src, "unlocked", out_dir=args.get("out_dir"))
        save_pdf(doc, out_path, garbage=3, encryption=pymupdf.PDF_ENCRYPT_NONE)
    return result([out_path], was_encrypted=was_encrypted, needed_password=needed_password)
