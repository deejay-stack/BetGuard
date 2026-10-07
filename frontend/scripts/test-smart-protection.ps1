param(
    [string]$ApiBaseUrl = 'http://127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
$apiAddress = $ApiBaseUrl.TrimEnd('/')
$health = Invoke-RestMethod "$apiAddress/health/detection" -TimeoutSec 15
if ($health.ready -ne $true) {
    throw 'The hostname detector is not ready. Start the backend and check its model artifacts.'
}
Write-Host "Detector ready: $($health.model_display_name)"

# These are regression cases for the current frozen hostname model and list.
# This checks the running API; it does not measure model accuracy or phone VPN coverage.
$cases = @(
    @{ Domain = 'stake.com'; Action = 'BLOCK'; Intervention = 'BLOCK'; Source = 'verified_gambling_blocklist' },
    @{ Domain = 'casino.fanatics.com'; Action = 'BLOCK'; Intervention = 'BLOCK'; Source = 'ml_high_risk' },
    @{ Domain = 'wikipedia.org'; Action = 'ALLOW'; Intervention = 'NONE'; Source = 'ml_low_risk' },
    @{ Domain = 'microsoft.com'; Action = 'ALLOW'; Intervention = 'WARN'; Source = 'ml_warning' }
)
$body = @{ domains = @($cases | ForEach-Object { $_.Domain }) } | ConvertTo-Json
$response = Invoke-RestMethod "$apiAddress/v1/domain/check-batch" -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 15
if ($response.ok -ne $true -or $response.count -ne $cases.Count -or @($response.results).Count -ne $cases.Count) {
    throw 'The detector returned an incomplete response.'
}

$report = for ($index = 0; $index -lt $cases.Count; $index++) {
    $expected = $cases[$index]
    $actual = $response.results[$index]
    if ($actual.domain -ne $expected.Domain -or
        $actual.enforcement_action -ne $expected.Action -or
        $actual.intervention -ne $expected.Intervention -or
        $actual.decision_source -ne $expected.Source) {
        throw "Unexpected result for $($expected.Domain). Inspect /v1/domain/check; if you deliberately changed the deployed model or list, review these expected cases."
    }
    if ($expected.Source -like 'ml_*' -and ($null -eq $actual.ml_score -or $actual.ml_score -lt 0 -or $actual.ml_score -gt 1)) {
        throw "Missing or invalid ML score for $($expected.Domain)."
    }
    [PSCustomObject]@{
        Domain = $actual.domain
        Action = $actual.enforcement_action
        Advice = $actual.intervention
        Source = $actual.decision_source
        Score = $actual.ml_score
    }
}
$report | Format-Table -AutoSize
Write-Host 'PASS: running detector returned the expected list, ML Block, Allow and WARN decisions.'
Write-Host 'microsoft.com is a WARN regression case, not evidence that Microsoft is gambling.'
Write-Host 'Next: enable Smart protection on the phone, restart Chrome and check fresh DNS requests in Activity. See docs/APP_GUIDE.md.'
