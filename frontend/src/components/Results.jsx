import RiskBadge from './RiskBadge.jsx'
import CoverageNote from './CoverageNote.jsx'
import FindingsTable from './FindingsTable.jsx'
import ThreadTimeline from './ThreadTimeline.jsx'
import HighlightedBody from './HighlightedBody.jsx'
import TacticList from './TacticList.jsx'
import ScoreBreakdown from './ScoreBreakdown.jsx'
import ClaimsTable from './ClaimsTable.jsx'
import HeaderFindings from './HeaderFindings.jsx'

// The report, in the order a reader needs it: the answer, how much it rests on, the findings, the conversation, the text, the tactics, then the working.
export default function Results({ report, explainStatus, explainError, explainRetryLeft, onExplain }) {
  return (
    <div className="flex flex-col gap-4">
      <RiskBadge report={report} />
      <CoverageNote report={report} />
      <FindingsTable report={report} />
      {report.thread && <ThreadTimeline thread={report.thread} />}
      <HighlightedBody report={report} explainStatus={explainStatus} explainError={explainError} retryLeft={explainRetryLeft} onExplain={onExplain} />
      <TacticList tactics={report.tactics} />
      <ScoreBreakdown detail={report.score_detail} />
      <ClaimsTable report={report} />
      <HeaderFindings findings={report.header_findings} />
    </div>
  )
}
