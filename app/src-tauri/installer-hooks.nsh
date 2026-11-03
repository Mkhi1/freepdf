; Lets "Nearby devices" reach this PC: UDP 47820 for discovery, TCP for transfers.
!define FREEPDF_FW_RULE "Free PDF nearby devices"

!macro NSIS_HOOK_POSTINSTALL
  nsExec::Exec 'netsh advfirewall firewall delete rule name="${FREEPDF_FW_RULE}"'
  nsExec::Exec 'netsh advfirewall firewall add rule name="${FREEPDF_FW_RULE}" dir=in action=allow program="$INSTDIR\${MAINBINARYNAME}.exe" protocol=TCP profile=private,domain enable=yes'
  nsExec::Exec 'netsh advfirewall firewall add rule name="${FREEPDF_FW_RULE}" dir=in action=allow program="$INSTDIR\${MAINBINARYNAME}.exe" protocol=UDP profile=private,domain enable=yes'
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  nsExec::Exec 'netsh advfirewall firewall delete rule name="${FREEPDF_FW_RULE}"'
!macroend
