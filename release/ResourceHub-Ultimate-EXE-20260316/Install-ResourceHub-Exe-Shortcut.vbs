Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
desktopPath = shell.SpecialFolders("Desktop")
shortcutPath = desktopPath & "\Resource Hub.exe.lnk"
targetPath = appDir & "\ResourceHubPython.exe"
iconPath = appDir & "\DesktopShortcut.ico"

If Not fso.FileExists(iconPath) Then
    iconPath = appDir & "\LinkHub.ico"
End If

Set shortcut = shell.CreateShortcut(shortcutPath)
shortcut.TargetPath = targetPath
shortcut.WorkingDirectory = appDir
shortcut.IconLocation = iconPath & ",0"
shortcut.WindowStyle = 1
shortcut.Description = "Resource Hub Python Desktop EXE"
shortcut.Save

MsgBox "Desktop shortcut created: " & shortcutPath, 64, "Resource Hub EXE"
