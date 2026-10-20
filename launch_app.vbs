Set oWS = CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")

' Xoa sach cac bien moi truong noi bo PyInstaller neu chay qua update
On Error Resume Next
oWS.Environment("PROCESS").Remove("_PYI_PARENT_PROCESS_LEVEL")
oWS.Environment("PROCESS").Remove("_MEIPASS2")
oWS.Environment("PROCESS").Remove("_MEIPASS")
oWS.Environment("PROCESS").Remove("_PYI_APPLICATION_HOME_DIR")
oWS.Environment("PROCESS").Remove("_PYI_ARCHIVE_FILE")
oWS.Environment("PROCESS").Remove("_PYI_SPLASH_IPC")
On Error GoTo 0

' 1. Lay thu muc chua chinh file script nay (Giup Tool hoat dong linh hoat o moi may tinh va o dia)
scriptDir = oFSO.GetParentFolderName(WScript.ScriptFullName)

' 2. Kiem tra xem TS_Origin_Control_V3 (exe hoac python) da chay chua de tranh khoi chay trung lap
isAlreadyRunning = False
Set oWMIService = GetObject("winmgmts:\\.\root\cimv2")

' Kiem tra tien trinh .exe
Set colExe = oWMIService.ExecQuery("Select * from Win32_Process Where Name = 'TS_Origin_Control_V3.exe'")
If colExe.Count > 0 Then
    isAlreadyRunning = True
End If

' Kiem tra tien trinh python dang chay main_v3.py
If Not isAlreadyRunning Then
    Set colPy = oWMIService.ExecQuery("Select * from Win32_Process Where Name = 'python.exe' or Name = 'pythonw.exe'")
    For Each p In colPy
        If InStr(1, p.CommandLine, "main_v3.py", 1) > 0 Then
            isAlreadyRunning = True
            Exit For
        End If
    Next
End If

' 3. Neu chua chay thi khoi chay app
If Not isAlreadyRunning Then
    exePath = scriptDir & "\TS_Origin_Control_V3.exe"
    
    If oFSO.FileExists(exePath) Then
        ' Khi chay trong thu muc dist co file exe
        oWS.CurrentDirectory = scriptDir
        oWS.Run """" & exePath & """", 1, False
        WScript.Sleep 1500
    ElseIf oFSO.FileExists(scriptDir & "\main_v3.py") Then
        ' Khi chay trong thu muc ma nguon: uu tien chay truc tiep main_v3.py
        oWS.CurrentDirectory = scriptDir
        oWS.Run "python main_v3.py", 1, False
        WScript.Sleep 2000
    ElseIf oFSO.FileExists(scriptDir & "\dist\TS_Origin_Control_V3.exe") Then
        oWS.CurrentDirectory = scriptDir & "\dist"
        oWS.Run """" & scriptDir & "\dist\TS_Origin_Control_V3.exe""", 1, False
        WScript.Sleep 1500
    End If
End If

' 4. Bat Cua So Web App Dien Thoai (Cong 8080 Hub Gateway cho V3)
chromePath1 = "C:\Program Files\Google\Chrome\Application\chrome.exe"
chromePath2 = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
edgePath1 = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
edgePath2 = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
chromeArgs = "--app=http://localhost:8080 --window-size=510,720"

browserPath = ""
If oFSO.FileExists(chromePath1) Then
    browserPath = chromePath1
ElseIf oFSO.FileExists(chromePath2) Then
    browserPath = chromePath2
ElseIf oFSO.FileExists(edgePath1) Then
    browserPath = edgePath1
ElseIf oFSO.FileExists(edgePath2) Then
    browserPath = edgePath2
End If

If browserPath <> "" Then
    oWS.Run """" & browserPath & """ " & chromeArgs, 1, False
Else
    oWS.Run "http://localhost:8080", 1, False
End If
