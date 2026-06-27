' Double-click to launch the Sagemcom presence tray app with NO console window.
' Equivalent to running `pythonw tray.py` from the agent\ folder.
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
' window style 0 = hidden, don't wait for it to exit
sh.Run "pythonw """ & dir & "\tray.py""", 0, False
