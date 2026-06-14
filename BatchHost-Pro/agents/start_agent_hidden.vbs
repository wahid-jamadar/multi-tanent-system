Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run chr(34) & strPath & "\batchhost-pro_agent.bat" & Chr(34), 0
Set WshShell = Nothing
