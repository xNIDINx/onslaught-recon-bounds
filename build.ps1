param(
    [string]$Python = 'C:\Python27\python.exe',
    [string]$ExternalTools = (Join-Path $PSScriptRoot 'external'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist')
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$packageDir = Join-Path $projectRoot 'build-artifacts\package'
$modsDir = Join-Path $packageDir 'res\scripts\client\gui\mods'
$distDir = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $modsDir,$distDir -Force | Out-Null
$modules = @('mod_nidin_onslaught_recon','nidin_smoke/__init__','nidin_smoke/bounds','nidin_smoke/geometry','nidin_smoke/terrain','nidin_smoke/ui')
foreach($module in $modules) {
    $source = Join-Path $projectRoot "source\res\scripts\client\gui\mods\$module.py"
    $bytecode = Join-Path $modsDir "$module.pyc"
    New-Item -ItemType Directory -Path (Split-Path -Parent $bytecode) -Force | Out-Null
    & $python -B -c 'import py_compile,sys; assert sys.version_info[:2] == (2,7); py_compile.compile(sys.argv[1],cfile=sys.argv[2],dfile=sys.argv[3],doraise=True)' $source $bytecode "$module.py"
    if($LASTEXITCODE -ne 0) { throw "Python 2.7 compilation failed: $module" }
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'source\meta.xml') -Destination (Join-Path $packageDir 'meta.xml')
$flashDir = Join-Path $packageDir 'res\gui\flash'
New-Item -ItemType Directory -Path $flashDir -Force | Out-Null
$toolsDir = [IO.Path]::GetFullPath($ExternalTools)
$flexDir = Join-Path $toolsDir 'apache-flex-sdk-4.16.1'
$env:PLAYERGLOBAL_HOME = Join-Path $toolsDir 'playerglobal'
& java -jar "$flexDir/lib/mxmlc.jar" "+flexlib=$flexDir/frameworks" "-compiler.external-library-path+=$toolsDir/wot-game-api.swc" '-target-player=32.0' '-debug=false' '-compiler.omit-trace-statements=false' "-output=$flashDir/nidinSmokeContour.swf" "$projectRoot/actionscript/NidinSmokeContourUI.as"
if($LASTEXITCODE -ne 0) { throw 'Contour SWF compilation failed' }
[xml]$meta = Get-Content -LiteralPath (Join-Path $packageDir 'meta.xml')
if($meta.root.id -ne 'nidin.onslaught_recon_bounds') { throw 'Wrong mod id' }
$output = Join-Path $distDir "$($meta.root.id)_$($meta.root.version).mtmod"
$files = @('meta.xml', 'res/gui/flash/nidinSmokeContour.swf') + @($modules | ForEach-Object { "res/scripts/client/gui/mods/$_.pyc" })
& $python -B (Join-Path $projectRoot 'tools\package_mtmod.py') $packageDir $output @files
if($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
$hash = Get-FileHash -LiteralPath $output -Algorithm SHA256
"$($hash.Hash.ToLowerInvariant())  $([IO.Path]::GetFileName($output))" | Set-Content -LiteralPath ([IO.Path]::ChangeExtension($output, '.sha256')) -Encoding ASCII
$hash
