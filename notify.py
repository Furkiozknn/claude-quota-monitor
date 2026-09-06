"""Windows bildirimi — bagimliliksiz.

Ucuncu taraf paket (win10toast, plyer) kullanmiyoruz; projenin "sifir
bagimlilik" sozu bildirim icin de gecerli. PowerShell zaten Windows'ta var,
onun uzerinden WinRT toast gonderiyoruz.

Iki kademe:
  1. WinRT ToastNotification — Windows 10/11'in yerel bildirimi.
  2. NotifyIcon balonu — WinRT calismazsa yedek.

Windows disinda sessizce False doner; cagiran taraf bunu sorun saymaz.
"""

from __future__ import annotations

import os
import subprocess
from xml.sax.saxutils import escape as xml_escape

# PowerShell'in kayitli AppID'si. Kendi uygulamamizi Baslat menusune
# kaydetmedigimiz icin toast'i onun kimligiyle gonderiyoruz — aksi halde
# Windows bildirimi sessizce yutuyor.
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

_TOAST_PS = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml(@"
__PAYLOAD__
"@)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('__APPID__').Show($toast)
"""

_BALLOON_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Warning
$n.Visible = $true
$n.ShowBalloonTip(8000, '__TITLE__', '__MSG__', [System.Windows.Forms.ToolTipIcon]::Warning)
Start-Sleep -Seconds 9
$n.Dispose()
"""


def _run_ps(script: str, timeout: int = 20) -> bool:
    """PowerShell'i stdin uzerinden calistirir.

    Script'i komut satirina gommek yerine stdin'e veriyoruz; boylece
    tirnak/ters boluk kacislariyla ugrasmiyoruz.
    """
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "-"],
            input=script, text=True, capture_output=True,
            timeout=timeout, creationflags=flags,
        )
        return proc.returncode == 0
    except Exception:
        return False


def notify(title: str, message: str) -> bool:
    """Bildirim gonderir. Basarili olursa True.

    Cagiran taraf donus degerini kontrol etmek zorunda degil — bildirim
    gonderilemedi diye izleme durmamali.
    """
    if os.name != "nt":
        return False

    payload = (
        '<toast activationType="protocol" launch="http://127.0.0.1:8110/">'
        "<visual><binding template=\"ToastGeneric\">"
        f"<text>{xml_escape(title)}</text>"
        f"<text>{xml_escape(message)}</text>"
        "</binding></visual>"
        "</toast>"
    )
    script = _TOAST_PS.replace("__PAYLOAD__", payload).replace("__APPID__", APP_ID)
    if _run_ps(script):
        return True

    # Yedek: klasik balon bildirimi
    safe_title = title.replace("'", "''")
    safe_msg = message.replace("'", "''")
    return _run_ps(
        _BALLOON_PS.replace("__TITLE__", safe_title).replace("__MSG__", safe_msg),
        timeout=25,
    )


if __name__ == "__main__":  # elle deneme: python notify.py
    ok = notify("Claude kota", "Bu bir deneme bildirimidir.")
    print("gonderildi" if ok else "gonderilemedi")
