$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$OutDir = Join-Path $Root "dist\launcher"
$OutExe = Join-Path $OutDir "seshat-tts.exe"
$BuildDir = Join-Path $Root "build\launcher"
$Source = Join-Path $BuildDir "SeshatTtsLauncher.cs"
$Project = Join-Path $BuildDir "SeshatTtsLauncher.csproj"
$Icon = Join-Path $Root "resources\seshat-tts.ico"
$BuildIcon = Join-Path $BuildDir "seshat-tts.ico"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
Get-ChildItem -Path (Join-Path $BuildDir "*") -File -Include "*.cs", "*.csproj" | Remove-Item -Force
foreach ($GeneratedDir in @("bin", "obj")) {
    $Path = Join-Path $BuildDir $GeneratedDir
    if (Test-Path $Path) {
        Remove-Item -Path $Path -Recurse -Force
    }
}
if (Test-Path $Icon) {
    Copy-Item -Path $Icon -Destination $BuildIcon -Force
}

@'
using System;
using System.Diagnostics;
using System.IO;

public static class SeshatTtsLauncher
{
    public static int Main(string[] args)
    {
        string exeDir = AppDomain.CurrentDomain.BaseDirectory;
        string root = Path.GetFullPath(Path.Combine(exeDir, "..", ".."));
        string venvPythonw = Path.Combine(root, ".venv", "Scripts", "pythonw.exe");
        string venvPython = Path.Combine(root, ".venv", "Scripts", "python.exe");

        string python = File.Exists(venvPythonw) ? venvPythonw :
            File.Exists(venvPython) ? venvPython :
            "pythonw.exe";

        string arguments = "-m seshat_tts";
        if (args.Length > 0)
        {
            arguments += " " + string.Join(" ", Array.ConvertAll(args, Quote));
        }

        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = python;
        start.Arguments = arguments;
        start.WorkingDirectory = root;
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        start.EnvironmentVariables["PYTHONPATH"] = Path.Combine(root, "src");

        try
        {
            Process process = Process.Start(start);
            return process == null ? 1 : 0;
        }
        catch
        {
            start.FileName = "python.exe";
            start.CreateNoWindow = false;
            Process process = Process.Start(start);
            return process == null ? 1 : 0;
        }
    }

    private static string Quote(string value)
    {
        if (value.IndexOfAny(new char[] {' ', '\t', '"'}) < 0)
        {
            return value;
        }
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}
'@ | Set-Content -Path $Source -Encoding UTF8

$compiler = Get-Command csc.exe -ErrorAction SilentlyContinue
if ($compiler) {
    $iconArg = if (Test-Path $Icon) { "/win32icon:$Icon" } else { $null }
    & $compiler.Source /nologo /target:winexe /out:$OutExe $iconArg $Source
} else {
    $dotnet = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if (-not $dotnet) {
        throw "No C# compiler found. Install the .NET SDK or add csc.exe to PATH."
    }

@'
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows</TargetFramework>
    <ImplicitUsings>disable</ImplicitUsings>
    <Nullable>disable</Nullable>
    <AssemblyName>seshat-tts</AssemblyName>
    <ApplicationIcon>seshat-tts.ico</ApplicationIcon>
  </PropertyGroup>
  <ItemGroup>
    <Content Include="seshat-tts.ico" />
  </ItemGroup>
</Project>
'@ | Set-Content -Path $Project -Encoding UTF8

    dotnet publish $Project -c Release -o $OutDir --nologo
}

Write-Host "Built fast launcher: $OutExe"
Write-Host "This launcher expects dependencies installed in .venv or the active Python environment."
