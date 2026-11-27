@echo off
setlocal
cd /d "%~dp0"
if exist MedGuide-8fb7441.zip (
  echo MedGuide-8fb7441.zip already exists. Move it first to rebuild it.
  pause
  exit /b 1
)
copy /b MedGuide-8fb7441.zip.part-00+MedGuide-8fb7441.zip.part-01+MedGuide-8fb7441.zip.part-02+MedGuide-8fb7441.zip.part-03+MedGuide-8fb7441.zip.part-04+MedGuide-8fb7441.zip.part-05+MedGuide-8fb7441.zip.part-06+MedGuide-8fb7441.zip.part-07 MedGuide-8fb7441.zip > nul
if errorlevel 1 (
  echo Could not assemble ZIP. Keep all downloaded parts together.
  pause
  exit /b 1
)
powershell -NoProfile -Command "if ((Get-FileHash -Algorithm SHA256 'MedGuide-8fb7441.zip').Hash -ne '2ea33b557594d7d8e6bc4b646884abe962a3cfecd2e3e26fb4e7462d1ba39ab9') { exit 1 }"
if errorlevel 1 (
  echo ZIP checksum verification failed. Download the parts again.
  pause
  exit /b 1
)
echo Created and verified MedGuide-8fb7441.zip
pause
