# Adds Free PDF to right-click and "Open with" for PDF files, for this Windows user only.
# It does not change the default PDF app and does not need admin rights.
$exe = "$env:LOCALAPPDATA\Programs\FreePDF\Free PDF.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "Free PDF is not installed at $exe" }

$command = "`"$exe`" `"%1`""
$icon = "`"$exe`",0"
$classes = 'Software\Classes'

function Set-RegistryValue([string]$subKey, [string]$name, [string]$value) {
    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($subKey)
    try { $key.SetValue($name, $value) } finally { $key.Close() }
}

Set-RegistryValue "$classes\FreePDF.Document" '' 'PDF Document'
Set-RegistryValue "$classes\FreePDF.Document\DefaultIcon" '' $icon
Set-RegistryValue "$classes\FreePDF.Document\shell\open\command" '' $command
Set-RegistryValue "$classes\.pdf\OpenWithProgids" 'FreePDF.Document' ''

Set-RegistryValue "$classes\Applications\Free PDF.exe" 'FriendlyAppName' 'Free PDF'
Set-RegistryValue "$classes\Applications\Free PDF.exe\SupportedTypes" '.pdf' ''
Set-RegistryValue "$classes\Applications\Free PDF.exe\shell\open\command" '' $command

Set-RegistryValue "$classes\SystemFileAssociations\.pdf\shell\FreePDF" '' 'Open with Free PDF'
Set-RegistryValue "$classes\SystemFileAssociations\.pdf\shell\FreePDF" 'Icon' $icon
Set-RegistryValue "$classes\SystemFileAssociations\.pdf\shell\FreePDF\command" '' $command

Add-Type -Namespace FreePdf -Name Shell -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int eventId, uint flags, System.IntPtr item1, System.IntPtr item2);
'@
$associationsChanged = 0x08000000
[FreePdf.Shell]::SHChangeNotify($associationsChanged, 0, [IntPtr]::Zero, [IntPtr]::Zero)
