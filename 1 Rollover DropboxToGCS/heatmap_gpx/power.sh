# PowerShell script to run closer.py on mtb.gpx and gravel.gpx

# Set the path to your Python interpreter if needed
$python = "py"  # або повний шлях, наприклад: "C:\Python39\python.exe"

# Шлях до скрипта
$script = ".\closer.py"

# Вхідні файли
$files = @(".\mtb.gpx", ".\gravel.gpx")

# Запуск для кожного файлу
foreach ($file in $files) {
    Write-Host "Running $script on $file..."
    & $python $script $file
}
