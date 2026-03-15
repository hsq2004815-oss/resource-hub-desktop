Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run Chr(34) & appDir & "\start-resource-hub-python.bat" & Chr(34), 0, False
