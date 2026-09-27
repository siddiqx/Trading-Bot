<#
.SYNOPSIS
    End-to-End Local Webhook Verification Script for Forex Live Signal Bot
.DESCRIPTION
    Tests the FastAPI health check, submits a test signal payload with environment=TEST,
    verifies duplicate protection, and checks SQLite database stats.
#>

$BaseUrl = "http://localhost:8000"
$Secret = "test-secret-key-12345"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " 1. TESTING HEALTH ENDPOINT (GET /health)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
    Write-Host "Health Check Response:" -ForegroundColor Green
    $health | Format-Custom
} catch {
    Write-Host "Failed to connect to $BaseUrl/health. Is the server running?" -ForegroundColor Red
    Write-Host "Run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host " 2. SENDING SIMULATED TEST SIGNAL (POST /webhook/tradingview)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

$testSignalId = "TEST_EURUSD_1H_" + (Get-Date -Format "yyyyMMddHHmmss")

$payload = @{
    event = "forex_signal"
    strategy = "adaptive_trend_momentum_breakout"
    version = "1.0.0"
    symbol = "EURUSD"
    exchange = "FX"
    timeframe = "60"
    direction = "LONG"
    signal_time = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    price = 1.08500
    entry = 1.08500
    stop_loss = 1.08300
    take_profit = 1.08900
    risk_reward = 2.0
    signal_score = 85.0
    adx = 28.5
    atr = 0.00114
    roc = 0.42
    candle_body_ratio = 0.80
    suggested_lots = 0.50
    risk_percent = 1.0
    entry_type = "ORDER_BLOCK_FIB_CONFLUENCE"
    entry_range_min = 1.08380
    entry_range_max = 1.08480
    order_block_high = 1.08480
    order_block_low = 1.08280
    fib_50 = 1.08420
    fib_618 = 1.08350
    fib_ext_tp = 1.08950
    rsi = 64.5
    htf_regime = "BULLISH"
    breakout_length = 48
    atr_multiplier = 1.5
    strategy_version = "1.0.0"
    webhook_secret = $Secret
    environment = "TEST"
    signal_id = $testSignalId
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/webhook/tradingview" -Method Post -Body $payload -ContentType "application/json"
    Write-Host "Webhook Accepted Response:" -ForegroundColor Green
    $response | Format-Custom
} catch {
    Write-Host "Error sending webhook: $_" -ForegroundColor Red
    exit 1
}

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host " 3. TESTING DUPLICATE PROTECTION (RE-SENDING SAME SIGNAL)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
try {
    $dupResponse = Invoke-RestMethod -Uri "$BaseUrl/webhook/tradingview" -Method Post -Body $payload -ContentType "application/json"
    Write-Host "Duplicate Check Response:" -ForegroundColor Yellow
    $dupResponse | Format-Custom
} catch {
    Write-Host "Duplicate check request failed: $_" -ForegroundColor Red
}

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host " 4. VERIFYING DATABASE STATS (GET /webhook/stats)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
try {
    $stats = Invoke-RestMethod -Uri "$BaseUrl/webhook/stats" -Method Get
    Write-Host "Database Statistics:" -ForegroundColor Green
    $stats | Format-Custom
} catch {
    Write-Host "Failed to fetch stats: $_" -ForegroundColor Red
}

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host " 5. VERIFYING MOST RECENT SIGNAL (GET /webhook/last)" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
try {
    $lastSignal = Invoke-RestMethod -Uri "$BaseUrl/webhook/last" -Method Get
    Write-Host "Last Recorded Signal in SQLite:" -ForegroundColor Green
    $lastSignal | Format-Custom
} catch {
    Write-Host "Failed to fetch last signal: $_" -ForegroundColor Red
}

Write-Host "`n>>> LOCAL END-TO-END TEST COMPLETED SUCCESSFULLY! <<<" -ForegroundColor Green
