; Lets "Nearby devices" reach this PC: UDP 47820 for discovery, TCP for transfers.
!define FREEPDF_FW_RULE "Free PDF nearby devices"

; PDF file type. Kept as "FreePDF.Document" so a PDF default already chosen in
; Windows keeps working; its icon and command must point at the installed exe,
; otherwise Explorer shows a blank icon for every PDF.
!define FREEPDF_PROGID "FreePDF.Document"
!define FREEPDF_EXE "$INSTDIR\${MAINBINARYNAME}.exe"
!ifndef SHCNE_ASSOCCHANGED
  !define SHCNE_ASSOCCHANGED 0x08000000
!endif

!macro FREEPDF_REMOVE_OLD_USER_KEYS
  ; Left by the old per-user install (install\register-right-click.ps1). They
  ; override the machine keys below and point at an exe that no longer exists.
  DeleteRegKey HKCU "Software\Classes\${FREEPDF_PROGID}"
  DeleteRegKey HKCU "Software\Classes\Applications\Free PDF.exe"
  DeleteRegKey HKCU "Software\Classes\SystemFileAssociations\.pdf\shell\FreePDF"
!macroend

!macro NSIS_HOOK_PREINSTALL
  ; The in-app updater starts this installer while Free PDF is still closing, and
  ; the built-in check then fails with "Failed to kill Free PDF". Give it up to
  ; 15 s to exit, then force it closed, so the update always goes through.
  ${If} $UpdateMode = 1
  ${OrIf} $PassiveMode = 1
    nsExec::Exec `powershell -NoProfile -ExecutionPolicy Bypass -Command "$$p = Get-Process -Name '${MAINBINARYNAME}' -ErrorAction SilentlyContinue | Where-Object { $$_.Path -eq '${FREEPDF_EXE}' }; if ($$p) { $$p | Wait-Process -Timeout 15 -ErrorAction SilentlyContinue; $$p | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500 }"`
    Pop $0
  ${EndIf}
!macroend

!macro NSIS_HOOK_POSTINSTALL
  nsExec::Exec 'netsh advfirewall firewall delete rule name="${FREEPDF_FW_RULE}"'
  nsExec::Exec 'netsh advfirewall firewall add rule name="${FREEPDF_FW_RULE}" dir=in action=allow program="${FREEPDF_EXE}" protocol=TCP profile=private,domain enable=yes'
  nsExec::Exec 'netsh advfirewall firewall add rule name="${FREEPDF_FW_RULE}" dir=in action=allow program="${FREEPDF_EXE}" protocol=UDP profile=private,domain enable=yes'

  !insertmacro FREEPDF_REMOVE_OLD_USER_KEYS

  WriteRegStr HKLM "Software\Classes\${FREEPDF_PROGID}" "" "PDF Document"
  WriteRegStr HKLM "Software\Classes\${FREEPDF_PROGID}\DefaultIcon" "" '"${FREEPDF_EXE}",0'
  WriteRegStr HKLM "Software\Classes\${FREEPDF_PROGID}\shell\open\command" "" '"${FREEPDF_EXE}" "%1"'
  WriteRegStr HKLM "Software\Classes\.pdf\OpenWithProgids" "${FREEPDF_PROGID}" ""

  WriteRegStr HKLM "Software\Classes\Applications\${MAINBINARYNAME}.exe" "FriendlyAppName" "Free PDF"
  WriteRegStr HKLM "Software\Classes\Applications\${MAINBINARYNAME}.exe\SupportedTypes" ".pdf" ""
  WriteRegStr HKLM "Software\Classes\Applications\${MAINBINARYNAME}.exe\shell\open\command" "" '"${FREEPDF_EXE}" "%1"'

  WriteRegStr HKLM "Software\Classes\SystemFileAssociations\.pdf\shell\FreePDF" "" "Open with Free PDF"
  WriteRegStr HKLM "Software\Classes\SystemFileAssociations\.pdf\shell\FreePDF" "Icon" '"${FREEPDF_EXE}",0'
  WriteRegStr HKLM "Software\Classes\SystemFileAssociations\.pdf\shell\FreePDF\command" "" '"${FREEPDF_EXE}" "%1"'

  System::Call 'shell32::SHChangeNotify(i ${SHCNE_ASSOCCHANGED}, i 0, p 0, p 0)'
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'netsh advfirewall firewall delete rule name="${FREEPDF_FW_RULE}"'
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Skip during an update: the updater uninstalls then reinstalls, and dropping
  ; the file type in between would reset the user's PDF default.
  ${If} $UpdateMode <> 1
    DeleteRegKey HKLM "Software\Classes\${FREEPDF_PROGID}"
    DeleteRegValue HKLM "Software\Classes\.pdf\OpenWithProgids" "${FREEPDF_PROGID}"
    DeleteRegKey HKLM "Software\Classes\Applications\${MAINBINARYNAME}.exe"
    DeleteRegKey HKLM "Software\Classes\SystemFileAssociations\.pdf\shell\FreePDF"
    !insertmacro FREEPDF_REMOVE_OLD_USER_KEYS
    System::Call 'shell32::SHChangeNotify(i ${SHCNE_ASSOCCHANGED}, i 0, p 0, p 0)'
  ${EndIf}
!macroend
