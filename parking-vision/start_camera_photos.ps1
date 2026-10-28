param(
  [int]$Camera = 1,
  [string]$Facility = "home-test-001",
  [string]$Email = "",
  [string]$Python = "",
  [switch]$PublicPhotos
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Camera -lt 0) { throw "Camera number must be 0 or greater." }
$candidates = @()
if ($Python) { $candidates = @($Python) } else {
  $candidates = @(
    (Join-Path $PSScriptRoot ".venv-photos\Scripts\python.exe"),
    (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
    (Join-Path $env:USERPROFILE "parking-vision\.venv-cpu\Scripts\python.exe"),
    (Join-Path $env:USERPROFILE "parking-yolo-home\.venv-gpu\Scripts\python.exe"),
    "python"
  )
}
$pythonCommand = $null
foreach ($candidate in $candidates) {
  if ($candidate -ne "python" -and -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
  try {
    & $candidate -c "import sys, cv2; sys.exit(0 if sys.version_info >= (3,10) else 1)" *> $null
    if ($LASTEXITCODE -eq 0) { $pythonCommand = $candidate; break }
  } catch { }
}
if (-not $pythonCommand) {
  throw "Python 3.10+ with OpenCV was not found. Specify -Python with your research environment's python.exe."
}
$arguments = @("publish_camera.py", "--camera", [string]$Camera, "--facility", $Facility)
if ($Email) { $arguments += @("--email", $Email) }
if ($PublicPhotos) { $arguments += "--public" }
& $pythonCommand @arguments
if ($LASTEXITCODE -ne 0) { throw "Camera photo publishing stopped with an error. Check the message above." }
