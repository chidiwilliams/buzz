$root = 'C:\Users\idoci\AppData\Local\Buzz\Buzz\Cache\models'
Get-ChildItem $root -Directory | ForEach-Object {
    $sz = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    $mb = [math]::Round($sz / 1MB, 1)
    Write-Host ("{0,-45} {1,8} MB" -f $_.Name, $mb)
}
