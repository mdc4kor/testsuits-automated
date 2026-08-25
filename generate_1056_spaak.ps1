param(
  [string]$FnId = 'FNID_1056',
  [string]$OutputFile = '1056.can',
  [string]$EcuQualifier = 'SPAAK',
  [string]$XmlPath = 'STLA_Testsuite.xml',
  [string]$CinPath = 'Masterdiag.cin'
)

Set-Location 'c:/Users/MDC4KOR/atm'

function Get-TestcaseBlocks {
  param([string]$Text)

  $blocks = @{}
  $rx = [regex]'(?m)^\s*testcase\s+([A-Za-z0-9_]+)\s*\(\)\s*\{'
  $matches = $rx.Matches($Text)
  foreach ($m in $matches) {
    $name = $m.Groups[1].Value
    $start = $m.Index + $m.Length
    $depth = 1
    $i = $start
    while ($i -lt $Text.Length -and $depth -gt 0) {
      $ch = $Text[$i]
      if ($ch -eq '{') { $depth++ }
      elseif ($ch -eq '}') { $depth-- }
      $i++
    }
    if ($depth -eq 0) {
      $blocks[$name] = $Text.Substring($start, $i - $start - 1)
    }
  }
  return $blocks
}

function Get-NameTokens {
  param([string]$Name)
  return [regex]::Split($Name, '[_\W]+') |
    Where-Object { $_ -and ($_ -notmatch '^\d+$') } |
    ForEach-Object { $_.ToLowerInvariant() }
}

function Resolve-SourceCase {
  param(
    [string]$XmlCaseName,
    [hashtable]$SourceBlocks
  )

  if ($SourceBlocks.ContainsKey($XmlCaseName)) { return $XmlCaseName }

  $idMatch = [regex]::Match($XmlCaseName, '_(\d+)$')
  if (-not $idMatch.Success) {
    throw "Cannot resolve testcase source for $XmlCaseName"
  }
  $id = $idMatch.Groups[1].Value

  $candidates = @($SourceBlocks.Keys | Where-Object { $_ -match ('_' + [regex]::Escape($id) + '$') })
  if ($candidates.Count -eq 0) {
    throw "No testcase with id $id found in Masterdiag.cin for $XmlCaseName"
  }
  if ($candidates.Count -eq 1) { return $candidates[0] }

  $xmlTokens = @(Get-NameTokens $XmlCaseName)
  $best = $candidates[0]
  $bestScore = -1
  foreach ($c in $candidates) {
    $tokens = @(Get-NameTokens $c)
    $score = (@($xmlTokens | Where-Object { $tokens -contains $_ })).Count
    if ($score -gt $bestScore) {
      $bestScore = $score
      $best = $c
    }
  }
  return $best
}

function Get-StepSpan {
  param([string]$Label)
  $nums = @($Label.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
  if ($nums.Count -gt 0 -and (@($nums | Where-Object { $_ -notmatch '^\d+$' }).Count -eq 0)) {
    return [Math]::Max(1, $nums.Count)
  }
  return 1
}

function Get-DerivedPosResp {
  param([string]$Req)
  $parts = @($Req.Split(' ') | Where-Object { $_ } | ForEach-Object { $_.ToUpperInvariant() })
  if ($parts.Count -lt 1) { return $null }
  if ($parts[0] -notmatch '^[0-9A-F]{2}$') { return $null }
  $sid = [Convert]::ToInt32($parts[0], 16)
  $pos = $sid + 64
  if ($pos -gt 255) { return $null }
  $parts[0] = ('{0:X2}' -f $pos)
  return ($parts -join ' ')
}

function Get-RespLen {
  param([string]$Resp)
  if ([string]::IsNullOrWhiteSpace($Resp)) { return 0 }
  return @($Resp.Split(' ') | Where-Object { $_ }).Count
}

function Get-ParsingRegion {
  param([string]$Body)
  $lines = @($Body -split "`r?`n")
  $start = -1
  $end = $lines.Count

  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '(?i)teststep\s*\(') {
      $start = $i
      break
    }
  }
  if ($start -lt 0) {
    return @()
  }

  for ($i = $start; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '(?i)testcasecomment\s*\(\s*"post\s*condition') {
      $end = $i
      break
    }
  }

  return ,($lines[$start..([Math]::Max($start, $end)-1)])
}

function Get-Events {
  param([string]$Body)

  $actions = Get-ParsingRegion $Body
  $events = New-Object System.Collections.Generic.List[object]
  $pendingLabel = $null
  $pendingDesc = $null

  function Get-LastTwoQuoted {
    param([string]$Text)
    $qs = [regex]::Matches($Text, '"([^"]*)"') | ForEach-Object { $_.Groups[1].Value }
    if ($qs.Count -lt 2) { return $null }
    return ,@($qs[$qs.Count - 2], $qs[$qs.Count - 1])
  }

  function Find-CommentedTemplateForLength {
    param(
      [string[]]$ActionLines,
      [int]$CurrentIndex,
      [string]$Req
    )

    $stepLabel = $null
    $stepDesc = $null
    $resp = $null
    $begin = [Math]::Max(0, $CurrentIndex - 6)

    for ($k = $CurrentIndex - 1; $k -ge $begin; $k--) {
      $t = $ActionLines[$k].Trim()
      if (-not $t) { continue }

      if ($null -eq $resp) {
        $mResp = [regex]::Match($t, '(?i)^//\s*SendDiag_Request_Verify_Response\s*\(\s*[^,]+\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\)')
        if ($mResp.Success) {
          $cReq = $mResp.Groups[1].Value
          if ($cReq.Trim().ToUpperInvariant() -eq $Req.Trim().ToUpperInvariant()) {
            $resp = $mResp.Groups[2].Value
          }
        }
      }

      if ($null -eq $stepDesc) {
        $mStep = [regex]::Match($t, '(?i)^//\s*TestStep\s*\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\)')
        if ($mStep.Success) {
          $stepLabel = $mStep.Groups[1].Value
          $stepDesc = $mStep.Groups[2].Value
          break
        }
      }
    }

    if ($null -eq $stepDesc) { return $null }
    return [pscustomobject]@{ Label = $stepLabel; Desc = $stepDesc; Resp = $resp }
  }

  function New-AutoDesc {
    param([string]$Req)
    if ([string]::IsNullOrWhiteSpace($Req)) { return 'Execute diagnostic request' }
    return ('Send request ' + $Req)
  }

  function Last-EventReqMatches {
    param([System.Collections.Generic.List[object]]$EventList, [string]$Req)
    if ($EventList.Count -eq 0) { return $false }
    $last = $EventList[$EventList.Count - 1]
    if ($null -eq $last) { return $false }
    if ($last.Kind -ne 'pos') { return $false }
    return (($last.Req + '').Trim().ToUpperInvariant() -eq ($Req + '').Trim().ToUpperInvariant())
  }

  for ($idx = 0; $idx -lt $actions.Count; $idx++) {
    $line = $actions[$idx]
    $s = $line.Trim()
    if (-not $s) { continue }
    if ($s -match '^(//|/\*)') { continue }

    if ($s -match '(?i)sendtesterpresent|diagstarttesterpresent') { continue }

    $mStep = [regex]::Match($s, '(?i)teststep\s*\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*\)')
    if ($mStep.Success) {
      if ($null -ne $pendingLabel) {
        $events.Add([pscustomobject]@{Kind='steponly'; Label=$pendingLabel; Desc=$pendingDesc; Req=''; Resp=''})
      }
      $pendingLabel = $mStep.Groups[1].Value
      $pendingDesc = $mStep.Groups[2].Value
      $afterStep = $s.Substring($mStep.Index + $mStep.Length).Trim()
      $afterStep = $afterStep.TrimStart(';').Trim()
      if (-not $afterStep) { continue }
      $s = $afterStep
    }

    if ($s -match '(?i)(Security_Access_11_12_Leaf_8|Security_.*Key_Access)\s*\(') {
      if ($null -ne $pendingLabel) {
        $events.Add([pscustomobject]@{Kind='security'; Label=$pendingLabel; Desc=$pendingDesc; Req=''; Resp=''})
        $pendingLabel = $null
        $pendingDesc = $null
      }
      continue
    }

    if ($s -match '(?i)^senddiag_request_verify_and_getresponse\s*\(') {
      $pair = Get-LastTwoQuoted $s
      if ($null -ne $pair) {
        $req = $pair[0]
        $resp = $pair[1]
        $kind = if ($resp.Trim().ToUpperInvariant().StartsWith('7F ')) { 'neg' } else { 'pos' }
        if ($null -eq $pendingLabel) {
          $events.Add([pscustomobject]@{Kind=$kind; Label=''; Desc=(New-AutoDesc $req); Req=$req; Resp=$resp})
        } else {
          $events.Add([pscustomobject]@{Kind=$kind; Label=$pendingLabel; Desc=$pendingDesc; Req=$req; Resp=$resp})
        }
      }
      $pendingLabel = $null
      $pendingDesc = $null
      continue
    }

    if ($s -match '(?i)^senddiag_request_verify_response\s*\(') {
      $pair = Get-LastTwoQuoted $s
      if ($null -ne $pair) {
        $req = $pair[0]
        $resp = $pair[1]
        $kind = if ($resp.Trim().ToUpperInvariant().StartsWith('7F ')) { 'neg' } else { 'pos' }
        if ($null -eq $pendingLabel) {
          $events.Add([pscustomobject]@{Kind=$kind; Label=''; Desc=(New-AutoDesc $req); Req=$req; Resp=$resp})
        } else {
          $events.Add([pscustomobject]@{Kind=$kind; Label=$pendingLabel; Desc=$pendingDesc; Req=$req; Resp=$resp})
        }
      }
      $pendingLabel = $null
      $pendingDesc = $null
      continue
    }

    if ($s -match '(?i)^senddiag_request_verify_negative_response\s*\(') {
      $pair = Get-LastTwoQuoted $s
      if ($null -ne $pair) {
        if ($null -eq $pendingLabel) {
          $events.Add([pscustomobject]@{Kind='neg'; Label=''; Desc=(New-AutoDesc $pair[0]); Req=$pair[0]; Resp=$pair[1]})
        } else {
          $events.Add([pscustomobject]@{Kind='neg'; Label=$pendingLabel; Desc=$pendingDesc; Req=$pair[0]; Resp=$pair[1]})
        }
      }
      $pendingLabel = $null
      $pendingDesc = $null
      continue
    }

    if ($s -match '(?i)^senddiag_request_neg\s*\(') {
      $pair = Get-LastTwoQuoted $s
      if ($null -ne $pair) {
        if ($null -eq $pendingLabel) {
          $events.Add([pscustomobject]@{Kind='neg'; Label=''; Desc=(New-AutoDesc $pair[0]); Req=$pair[0]; Resp=$pair[1]})
        } else {
          $events.Add([pscustomobject]@{Kind='neg'; Label=$pendingLabel; Desc=$pendingDesc; Req=$pair[0]; Resp=$pair[1]})
        }
      }
      $pendingLabel = $null
      $pendingDesc = $null
      continue
    }

    $mLen = [regex]::Match($s, '(?i)senddiag_request_verify_response_length\s*\(\s*[^,]+\s*,\s*"([^"]*)"\s*,\s*(\d+)\s*\)')
    if ($mLen.Success) {
      $req = $mLen.Groups[1].Value
      if ($null -eq $pendingLabel) {
        $tpl = Find-CommentedTemplateForLength -ActionLines $actions -CurrentIndex $idx -Req $req
        if ($null -ne $tpl) {
          $pendingLabel = $tpl.Label
          $pendingDesc = $tpl.Desc
          $resp = if ([string]::IsNullOrWhiteSpace($tpl.Resp)) { Get-DerivedPosResp $req } else { $tpl.Resp }
          if ($null -ne $resp) {
            $events.Add([pscustomobject]@{Kind='pos'; Label=$pendingLabel; Desc=$pendingDesc; Req=$req; Resp=$resp})
          }
          $pendingLabel = $null
          $pendingDesc = $null
          continue
        }
      }

      if ($null -ne $pendingLabel) {
        $resp = Get-DerivedPosResp $req
        if ($null -ne $resp) {
          $events.Add([pscustomobject]@{Kind='pos'; Label=$pendingLabel; Desc=$pendingDesc; Req=$req; Resp=$resp})
        }
        $pendingLabel = $null
        $pendingDesc = $null
        continue
      } else {
        if (Last-EventReqMatches -EventList $events -Req $req) {
          continue
        }
        $resp = Get-DerivedPosResp $req
        if ($null -ne $resp) {
          $events.Add([pscustomobject]@{Kind='pos'; Label=''; Desc=(New-AutoDesc $req); Req=$req; Resp=$resp})
        }
        continue
      }
    }

    if ($s -match '(?i)^(for\s*\(|if\s*\(|else\b|\{|\}|testwaitfortimeout\s*\(|teststeppass\s*\(|[A-Za-z_][A-Za-z0-9_\[\]]*\s*=)') {
      $events.Add([pscustomobject]@{Kind='raw'; Label=''; Desc=''; Req=''; Resp=''; Code=$s})
      continue
    }
  }

  if ($null -ne $pendingLabel) {
    $events.Add([pscustomobject]@{Kind='steponly'; Label=$pendingLabel; Desc=$pendingDesc; Req=''; Resp=''})
  }

  return $events
}

function Get-SourceStepCount {
  param([string]$Body)
  $actions = Get-ParsingRegion $Body
  $count = 0
  foreach ($line in $actions) {
    $s = $line.Trim()
    if (-not $s) { continue }
    if ($s -match '^(//|/\*)') { continue }
    if ($s -match '(?i)teststep\s*\(') { $count++ }
  }
  return $count
}

function Remove-LeadingDefaultSessionStep {
  param([System.Collections.Generic.List[object]]$Events)

  while ($Events.Count -gt 0) {
    $e = $Events[0]
    if ($null -eq $e) { break }
    if ($e.Kind -eq 'raw') { break }
    $req = (($e.Req + '').Trim().ToUpperInvariant())
    $desc = (($e.Desc + '').ToLowerInvariant())
    if ($req -eq '10 01' -and $desc -match 'default\s+diagnostic\s+session') {
      $Events.RemoveAt(0)
      continue
    }
    break
  }

  return $Events
}

function Should-SkipEvent {
  param($Event)

  if ($null -eq $Event) { return $false }
  if ($Event.Kind -eq 'raw') { return $false }

  $desc = (($Event.Desc + '').ToLowerInvariant())
  $req = (($Event.Req + '').Trim().ToUpperInvariant())

  if ($desc -match 'tester\s+present') { return $true }
  if ($req -eq '3E 00') { return $true }

  return $false
}

[xml]$xml = Get-Content $XmlPath
$group = $xml.SelectSingleNode(("//testgroup[@ident='{0}']" -f $FnId))
if ($null -eq $group) { throw ($FnId + ' not found') }
$cases = @($group.SelectNodes('.//capltestcase'))

$cinText = Get-Content $CinPath -Raw
$sourceBlocks = Get-TestcaseBlocks $cinText

$fnNumber = ($FnId -replace '(?i)^FNID_', '').Trim()
if ([string]::IsNullOrWhiteSpace($fnNumber)) { $fnNumber = '0000' }

$title = [string]$group.title
$title = $title -replace ('[_-]?' + [regex]::Escape($fnNumber) + '$'),' '
$title = $title.Trim()
$title = $title.Trim('_','-')
$suiteTag = if ($title) { ($fnNumber + '_' + $title) } else { $fnNumber }

$out = New-Object System.Text.StringBuilder
[void]$out.AppendLine(('//****************************TSU_{0}******************************************************************************//' -f $fnNumber))
[void]$out.AppendLine('')

$foundCases = New-Object System.Collections.Generic.List[string]
$missingCases = New-Object System.Collections.Generic.List[string]

foreach ($case in $cases) {
  $xmlName = [string]$case.name
  if ([string]::IsNullOrWhiteSpace($xmlName)) { continue }

  try {
    $sourceName = Resolve-SourceCase -XmlCaseName $xmlName -SourceBlocks $sourceBlocks
    $foundCases.Add(($xmlName + ' => ' + $sourceName))
  } catch {
    $missingCases.Add(($xmlName + ' => ' + $_.Exception.Message))
    continue
  }

  $body = [string]$sourceBlocks[$sourceName]
  $events = Get-Events $body
  $events = Remove-LeadingDefaultSessionStep -Events $events
  $sourceStepCount = Get-SourceStepCount $body

  if ($events.Count -ne $sourceStepCount) {
    Write-Output ("WARN_STEP_MISMATCH case={0} sourceSteps={1} parsedEvents={2}" -f $xmlName, $sourceStepCount, $events.Count)
  }

  [void]$out.AppendLine(("/// <{0}>" -f $suiteTag))
  [void]$out.AppendLine(("testcase {0}()" -f $xmlName))
  [void]$out.AppendLine('{')
  [void]$out.AppendLine(('  setLogFileName("reports\\Diag\\{0}\\{1}.asc");' -f $fnNumber, $xmlName))
  [void]$out.AppendLine('')

  [void]$out.AppendLine(('  PreCondition_Master({0});' -f $EcuQualifier))
  [void]$out.AppendLine('')

  $step = 1
  $emittedStep = $false
  foreach ($e in $events) {
    if ($e.Kind -eq 'raw') {
      [void]$out.AppendLine(('  ' + $e.Code))
      [void]$out.AppendLine('')
      continue
    }

    if (Should-SkipEvent -Event $e) {
      continue
    }

    $reqUpper = (($e.Req + '').Trim().ToUpperInvariant())
    if (-not $emittedStep -and $reqUpper -eq '10 01') {
      continue
    }

    $span = Get-StepSpan $e.Label
    if ($span -eq 1) {
      $lbl = "$step"
    } else {
      $lbl = ((0..($span-1)) | ForEach-Object { $step + $_ }) -join ','
    }
    $step += $span
    $emittedStep = $true

    [void]$out.AppendLine(('  TestStep("{0}","{1}");' -f $lbl, $e.Desc))
    if ($e.Kind -eq 'security') {
      [void]$out.AppendLine('  Security_Access_11_12_Leaf_8();')
    } elseif ($e.Kind -eq 'steponly') {
      # Keep step-only actions to avoid losing intent when no diagnostic call follows.
    } elseif ($e.Kind -eq 'neg') {
      [void]$out.AppendLine(('  SendDiag_Request_Neg(0, "{0}","{1}","{2}");' -f $EcuQualifier, $e.Req, $e.Resp))
    } else {
      if ([string]::IsNullOrWhiteSpace($e.Resp)) {
        [void]$out.AppendLine(('  SendDiag_Request_Verify_Response("{0}","{1}","");' -f $EcuQualifier, $e.Req))
      } else {
        $len = Get-RespLen $e.Resp
        [void]$out.AppendLine(('  SendDiag_Request_Verify_and_GetResponse("{0}","{1}","{2}", {3});' -f $EcuQualifier, $e.Req, $e.Resp, $len))
      }
    }
    [void]$out.AppendLine('')
  }

  [void]$out.AppendLine(('  PostCondition_Master({0});' -f $EcuQualifier))
  [void]$out.AppendLine('}')
  [void]$out.AppendLine('')
}

[IO.File]::WriteAllText((Join-Path (Get-Location) $OutputFile), $out.ToString(), [Text.Encoding]::UTF8)
Write-Output ('xml_cases=' + $cases.Count)
Write-Output ('generated_case_count=' + ([regex]::Matches($out.ToString(), '(?m)^testcase ').Count))
Write-Output ('found_case_count=' + $foundCases.Count)
Write-Output ('missing_case_count=' + $missingCases.Count)

if ($foundCases.Count -gt 0) {
  Write-Output 'FOUND_CASES_BEGIN'
  foreach ($f in $foundCases) {
    Write-Output ('FOUND ' + $f)
  }
  Write-Output 'FOUND_CASES_END'
}

if ($missingCases.Count -gt 0) {
  Write-Output 'MISSING_CASES_BEGIN'
  foreach ($m in $missingCases) {
    Write-Output ('MISSING ' + $m)
  }
  Write-Output 'MISSING_CASES_END'
}

Write-Output ('SPAAK_MASTER_' + $fnNumber + '_OK')
