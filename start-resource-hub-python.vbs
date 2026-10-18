Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
command = Chr(34) & appDir & "\start-resource-hub-python.bat" & Chr(34)

For i = 0 To WScript.Arguments.Count - 1
    argumentText = Replace(WScript.Arguments(i), Chr(34), Chr(34) & Chr(34))
    command = command & " " & Chr(34) & argumentText & Chr(34)
Next

shell.Run command, 0, False
