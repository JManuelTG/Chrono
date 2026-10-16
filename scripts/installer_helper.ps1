# ChronoRecovery Installer PowerShell Helper
param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("Install", "Uninstall", "CreateShortcuts", "RegisterAssociation", "CheckStatus")]
    [string]$Action,

    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\ChronoRecovery",
    [string]$SourceDir = $PSScriptRoot + "\.."
)

$ErrorActionPreference = "Stop"

function Notify-ExplorerAssociationChange {
    try {
        Add-Type -TypeDefinition @"
        using System;
        using System.Runtime.InteropServices;
        public class Win32Shell {
            [DllImport("shell32.dll", CharSet = CharSet.Auto, SetLastError = true)]
            public static extern void SHChangeNotify(int wEventId, int uFlags, IntPtr dwItem1, IntPtr dwItem2);
        }
"@ -ErrorAction SilentlyContinue
        [Win32Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
    } catch {
        # Fallback if Add-Type fails or is restricted
    }
}

function Set-ShortcutAdminFlag {
    param([string]$Path)
    try {
        if (Test-Path $Path) {
            $bytes = [System.IO.File]::ReadAllBytes($Path)
            if ($bytes.Length -gt 0x15) {
                $bytes[0x15] = $bytes[0x15] -bor 0x20
                [System.IO.File]::WriteAllBytes($Path, $bytes)
            }
        }
    } catch {
        Write-Warning "Could not set RunAsAdministrator flag on ${Path}: $_"
    }
}

function New-ChronoShortcut {
    param(
        [string]$ShortcutFile,
        [string]$TargetFile,
        [string]$WorkingDir,
        [string]$IconFile,
        [string]$Description,
        [switch]$Elevated
    )
    $parentDir = Split-Path -Parent $ShortcutFile
    if (-not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }

    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut($ShortcutFile)
    $shortcut.TargetPath = $TargetFile
    $shortcut.WorkingDirectory = $WorkingDir
    if (Test-Path $IconFile) {
        $shortcut.IconLocation = "$IconFile,0"
    }
    $shortcut.Description = $Description
    $shortcut.Save()

    if ($Elevated) {
        Set-ShortcutAdminFlag -Path $ShortcutFile
    }
}

function Register-RsfAssociation {
    param(
        [string]$ExePath,
        [string]$IconPath
    )
    Write-Host "[*] Registering .rsf file association..." -ForegroundColor Cyan

    $extKey = "HKCU:\Software\Classes\.rsf"
    New-Item -Path $extKey -Force | Out-Null
    Set-ItemProperty -Path $extKey -Name "(Default)" -Value "ChronoRecovery.RSF"
    Set-ItemProperty -Path $extKey -Name "Content Type" -Value "application/x-chronorecovery-session"

    $progKey = "HKCU:\Software\Classes\ChronoRecovery.RSF"
    New-Item -Path $progKey -Force | Out-Null
    Set-ItemProperty -Path $progKey -Name "(Default)" -Value "ChronoRecovery Scan Session"

    $iconKey = "$progKey\DefaultIcon"
    New-Item -Path $iconKey -Force | Out-Null
    Set-ItemProperty -Path $iconKey -Name "(Default)" -Value "`"$IconPath`",0"

    $cmdKey = "$progKey\shell\open\command"
    New-Item -Path $cmdKey -Force | Out-Null
    Set-ItemProperty -Path $cmdKey -Name "(Default)" -Value "`"$ExePath`" `"%1`""

    Notify-ExplorerAssociationChange
    Write-Host "[+] .rsf file association registered successfully." -ForegroundColor Green
}

function Unregister-RsfAssociation {
    Write-Host "[*] Unregistering .rsf file association..." -ForegroundColor Cyan
    Remove-Item -Path "HKCU:\Software\Classes\.rsf" -Recurse -ErrorAction SilentlyContinue
    Remove-Item -Path "HKCU:\Software\Classes\ChronoRecovery.RSF" -Recurse -ErrorAction SilentlyContinue
    Notify-ExplorerAssociationChange
    Write-Host "[+] .rsf file association removed." -ForegroundColor Green
}

function Add-ToUserPath {
    param([string]$PathToAdd)
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) {
        [Environment]::SetEnvironmentVariable("Path", $PathToAdd, "User")
        Write-Host "[+] Added $PathToAdd to User PATH." -ForegroundColor Green
        return
    }

    $parts = $userPath -split ';' | Where-Object { $_ -ne "" }
    if ($parts -notcontains $PathToAdd) {
        $newPath = ($parts + $PathToAdd) -join ';'
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "[+] Added $PathToAdd to User PATH." -ForegroundColor Green
    } else {
        Write-Host "[i] $PathToAdd is already in User PATH." -ForegroundColor Gray
    }
}

function Remove-FromUserPath {
    param([string]$PathToRemove)
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath) {
        $parts = $userPath -split ';' | Where-Object { $_ -ne "" -and $_ -ne $PathToRemove }
        $newPath = $parts -join ';'
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "[+] Removed $PathToRemove from User PATH." -ForegroundColor Green
    }
}

function Register-UninstallEntry {
    param(
        [string]$TargetDir,
        [string]$IconPath
    )
    $uninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ChronoRecovery"
    New-Item -Path $uninstKey -Force | Out-Null
    Set-ItemProperty -Path $uninstKey -Name "DisplayName" -Value "ChronoRecovery"
    Set-ItemProperty -Path $uninstKey -Name "DisplayVersion" -Value "1.0.0"
    Set-ItemProperty -Path $uninstKey -Name "Publisher" -Value "Jose Manuel TG"
    Set-ItemProperty -Path $uninstKey -Name "DisplayIcon" -Value "$IconPath"
    Set-ItemProperty -Path $uninstKey -Name "InstallLocation" -Value "$TargetDir"
    Set-ItemProperty -Path $uninstKey -Name "UninstallString" -Value "`"$TargetDir\uninstall.bat`""
    Set-ItemProperty -Path $uninstKey -Name "NoModify" -Value 1 -Type DWord
    Set-ItemProperty -Path $uninstKey -Name "NoRepair" -Value 1 -Type DWord
    Write-Host "[+] Registered in Windows Installed Apps." -ForegroundColor Green
}

function Unregister-UninstallEntry {
    Remove-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ChronoRecovery" -Recurse -ErrorAction SilentlyContinue
}

# --- Actions ---

switch ($Action) {
    "Install" {
        Write-Host "============================================================" -ForegroundColor Cyan
        Write-Host "         Installing ChronoRecovery to: " -ForegroundColor Cyan
        Write-Host "         $InstallDir" -ForegroundColor White
        Write-Host "============================================================" -ForegroundColor Cyan

        # 1. Create Target Directory
        if (-not (Test-Path $InstallDir)) {
            New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        }

        # 2. Check source binaries or build if needed
        $distDir = Join-Path $SourceDir "dist"
        $guiExe = Join-Path $distDir "ChronoRecovery.exe"
        $cliExe = Join-Path $distDir "chrono.exe"

        if (-not (Test-Path $guiExe)) {
            Write-Host "[*] Executable not found in dist. Compiling with build_exe.py..." -ForegroundColor Yellow
            $pyScript = Join-Path $SourceDir "build_exe.py"
            python $pyScript
        }

        # 3. Copy Executables and Assets
        Write-Host "[*] Deploying application files..." -ForegroundColor Cyan
        if (Test-Path $guiExe) {
            Copy-Item -Path $guiExe -Destination $InstallDir -Force
            Write-Host "  -> Copied ChronoRecovery.exe" -ForegroundColor Green
        } else {
            Write-Error "Could not locate or build ChronoRecovery.exe!"
            exit 1
        }

        if (Test-Path $cliExe) {
            Copy-Item -Path $cliExe -Destination $InstallDir -Force
            Write-Host "  -> Copied chrono.exe (CLI)" -ForegroundColor Green
        }

        # Assets
        $targetAssets = Join-Path $InstallDir "assets"
        $sourceAssets = Join-Path $SourceDir "assets"
        if (Test-Path $sourceAssets) {
            Copy-Item -Path $sourceAssets -Destination $InstallDir -Recurse -Force
            Write-Host "  -> Copied assets" -ForegroundColor Green
        }

        # Uninstaller script
        $uninstBatPath = Join-Path $InstallDir "uninstall.bat"
        $uninstContent = @"
@echo off
title ChronoRecovery - Uninstaller
echo ============================================================
echo   ChronoRecovery: Uninstalling Application
echo ============================================================
echo.
powershell.exe -ExecutionPolicy Bypass -File "%~dp0scripts\installer_helper.ps1" -Action Uninstall -InstallDir "%~dp0."
pause
"@
        # Copy scripts folder for uninstaller
        $targetScripts = Join-Path $InstallDir "scripts"
        New-Item -ItemType Directory -Path $targetScripts -Force | Out-Null
        Copy-Item -Path $PSCommandPath -Destination $targetScripts -Force
        Set-Content -Path $uninstBatPath -Value $uninstContent -Encoding ASCII

        # 4. Create Shortcuts
        $installedGuiExe = Join-Path $InstallDir "ChronoRecovery.exe"
        $iconFile = Join-Path $InstallDir "assets\icons\app_icon.ico"
        if (-not (Test-Path $iconFile)) {
            $iconFile = $installedGuiExe
        }

        # Desktop Shortcut
        $desktopPath = [Environment]::GetFolderPath("Desktop")
        $desktopLnk = Join-Path $desktopPath "ChronoRecovery.lnk"
        New-ChronoShortcut -ShortcutFile $desktopLnk -TargetFile $installedGuiExe -WorkingDir $InstallDir -IconFile $iconFile -Description "ChronoRecovery - Advanced Data Recovery Suite" -Elevated
        Write-Host "[+] Created Desktop Shortcut with Administrator Elevation." -ForegroundColor Green

        # Start Menu Shortcut
        $startMenuPrograms = [Environment]::GetFolderPath("Programs")
        $startMenuFolder = Join-Path $startMenuPrograms "ChronoRecovery"
        $startMenuLnk = Join-Path $startMenuFolder "ChronoRecovery.lnk"
        New-ChronoShortcut -ShortcutFile $startMenuLnk -TargetFile $installedGuiExe -WorkingDir $InstallDir -IconFile $iconFile -Description "ChronoRecovery - Advanced Data Recovery Suite" -Elevated

        $uninstLnk = Join-Path $startMenuFolder "Uninstall ChronoRecovery.lnk"
        New-ChronoShortcut -ShortcutFile $uninstLnk -TargetFile $uninstBatPath -WorkingDir $InstallDir -IconFile $iconFile -Description "Uninstall ChronoRecovery"
        Write-Host "[+] Created Start Menu Shortcuts." -ForegroundColor Green

        # 5. File Association
        Register-RsfAssociation -ExePath $installedGuiExe -IconPath $iconFile

        # 6. Add to User PATH
        Add-ToUserPath -PathToAdd $InstallDir

        # 7. Add Windows Uninstall Entry
        Register-UninstallEntry -TargetDir $InstallDir -IconPath $iconFile

        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "  [SUCCESS] ChronoRecovery successfully installed!" -ForegroundColor Green
        Write-Host "  Desktop & Start Menu shortcuts are ready." -ForegroundColor Green
        Write-Host "  Run 'chrono --help' from any terminal." -ForegroundColor Green
        Write-Host "============================================================" -ForegroundColor Green
    }

    "Uninstall" {
        Write-Host "============================================================" -ForegroundColor Yellow
        Write-Host "         Uninstalling ChronoRecovery..." -ForegroundColor Yellow
        Write-Host "============================================================" -ForegroundColor Yellow

        # 1. Remove Desktop Shortcut
        $desktopPath = [Environment]::GetFolderPath("Desktop")
        $desktopLnk = Join-Path $desktopPath "ChronoRecovery.lnk"
        if (Test-Path $desktopLnk) {
            Remove-Item -Path $desktopLnk -Force -ErrorAction SilentlyContinue
            Write-Host "[+] Removed Desktop shortcut." -ForegroundColor Green
        }

        # 2. Remove Start Menu folder
        $startMenuPrograms = [Environment]::GetFolderPath("Programs")
        $startMenuFolder = Join-Path $startMenuPrograms "ChronoRecovery"
        if (Test-Path $startMenuFolder) {
            Remove-Item -Path $startMenuFolder -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "[+] Removed Start Menu shortcuts." -ForegroundColor Green
        }

        # 3. Unregister File Association
        Unregister-RsfAssociation

        # 4. Remove from PATH
        Remove-FromUserPath -PathToRemove $InstallDir

        # 5. Remove Uninstall Registry
        Unregister-UninstallEntry

        # 6. Remove installed files
        if (Test-Path $InstallDir) {
            # In case running from within installDir, schedule self deletion
            Write-Host "[*] Removing installation files from $InstallDir..." -ForegroundColor Cyan
            try {
                Get-ChildItem -Path $InstallDir -Exclude "scripts", "uninstall.bat" -Recurse | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
                Write-Host "[+] Installation files removed." -ForegroundColor Green
            } catch {
                Write-Warning "Some files could not be removed immediately: $_"
            }
        }

        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "  [DONE] ChronoRecovery has been successfully uninstalled." -ForegroundColor Green
        Write-Host "============================================================" -ForegroundColor Green
    }

    "RegisterAssociation" {
        $icon = Join-Path $SourceDir "assets\icons\app_icon.ico"
        $exe = Join-Path $SourceDir "dist\ChronoRecovery.exe"
        if (-not (Test-Path $exe)) {
            $exe = (Get-Command pythonw).Source + ' "' + (Join-Path $SourceDir "recovery_gui.py") + '"'
        }
        Register-RsfAssociation -ExePath $exe -IconPath $icon
    }

    "CreateShortcuts" {
        $desktopPath = [Environment]::GetFolderPath("Desktop")
        $desktopLnk = Join-Path $desktopPath "ChronoRecovery.lnk"
        $icon = Join-Path $SourceDir "assets\icons\app_icon.ico"
        $exe = Join-Path $SourceDir "dist\ChronoRecovery.exe"
        if (Test-Path $exe) {
            New-ChronoShortcut -ShortcutFile $desktopLnk -TargetFile $exe -WorkingDir (Split-Path $exe) -IconFile $icon -Description "ChronoRecovery - Advanced Data Recovery Suite" -Elevated
            Write-Host "[+] Created Desktop Shortcut to $exe" -ForegroundColor Green
        } else {
            Write-Warning "ChronoRecovery.exe not found. Build it first with build_exe.py."
        }
    }

    "CheckStatus" {
        $guiExe = Join-Path $InstallDir "ChronoRecovery.exe"
        $installed = Test-Path $guiExe
        $rsfAssoc = (Get-ItemProperty -Path "HKCU:\Software\Classes\.rsf" -Name "(Default)" -ErrorAction SilentlyContinue)."(Default)"
        
        [PSCustomObject]@{
            Installed = $installed
            InstallDir = $InstallDir
            RsfAssociation = $rsfAssoc
        } | Format-List
    }
}
