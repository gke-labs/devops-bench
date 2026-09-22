// One leaderboard row — links to the detail page, carrying the active metric.
// Ported from the row template in app.js filterAndRender().

import { Link } from "react-router-dom";
import { SetupIdentity } from "./SetupIdentity.jsx";
import { setupScore, setupLabel } from "../lib/accessors.js";
import { formatMetric, metricBarFraction, TOKEN_BUCKET_COLORS } from "../lib/vocab.js";

// `metricMax` is the maximum value for this metric across the visible rows — for
// absolute metrics (latency, tokens, cost), the bar width directly represents
// the actual magnitude relative to this ceiling. Unused by percentage metrics.
export function LeaderboardRow({ setup, models, harnesses, metric, metricMax, metricBest, taskScope = "full" }) {
    const model = models[setup.model];
    const harness = harnesses[setup.harness];
    const score = setupScore(setup, metric);
    const scale = metricMax ?? metricBest;
    const barPct = metricBarFraction(metric, score, scale) * 100;
    const to = `/setup/${encodeURIComponent(setup.id)}?metric=${encodeURIComponent(metric)}${taskScope === "common" ? "&scope=common" : ""}`;

    const isTokens = metric === "tokens";
    const inputTokens = isTokens ? setupScore(setup, "inputTokens") : null;
    const cachedTokens = isTokens ? setupScore(setup, "cachedTokens") : null;
    const outputTokens = isTokens ? setupScore(setup, "outputTokens") : null;
    const sumBuckets = (inputTokens || 0) + (cachedTokens || 0) + (outputTokens || 0);

    const tokensTooltip = isTokens
        ? `Total: ${formatMetric("tokens", score)} (Input: ${formatMetric("inputTokens", inputTokens)}, Cached: ${formatMetric("cachedTokens", cachedTokens)}, Output: ${formatMetric("outputTokens", outputTokens)}) (task average)`
        : `${formatMetric(metric, score)} (task average)`;

    return (
        <Link
            to={to}
            aria-label={`View details for ${setupLabel(setup, models, harnesses)}`}
            className="relative px-6 py-4 flex flex-col sm:grid sm:grid-cols-12 gap-3 sm:gap-4 items-start sm:items-center hover:bg-slate-50/70 dark:hover:bg-slate-800/40 cursor-pointer transition-colors group select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-inset"
        >
            {/* Benchmark subject: model × harness pairing (grid only, so the × stays aligned) */}
            <div className="col-span-7 sm:col-span-7 grid grid-cols-[1fr_auto_1fr] items-center gap-1 sm:gap-2 w-full sm:w-auto pr-6 sm:pr-0">
                <SetupIdentity setup={setup} model={model} harness={harness} variant="row" />
            </div>

            {/* Score progression meter */}
            <div className="col-span-4 sm:col-span-4 flex flex-col justify-center gap-1 w-full sm:w-auto mt-2 sm:mt-0">
                <div className="flex items-center gap-3 w-full">
                    <span
                        title={tokensTooltip}
                        className="text-sm font-semibold text-slate-900 dark:text-slate-100 w-12 min-w-[48px]"
                    >
                        {formatMetric(metric, score)}
                    </span>
                    <div className="w-full bg-slate-100 dark:bg-slate-800 h-2 rounded-full overflow-hidden relative" title={tokensTooltip}>
                        {isTokens && sumBuckets > 0 ? (
                            <div className="progress-bar-fill h-full rounded-full flex overflow-hidden" style={{ width: `${barPct}%` }}>
                                {inputTokens > 0 && (
                                    <div
                                        style={{
                                            width: `${((inputTokens || 0) / sumBuckets) * 100}%`,
                                            backgroundColor: TOKEN_BUCKET_COLORS.tokensInput
                                        }}
                                        title={`Input: ${formatMetric("inputTokens", inputTokens)}`}
                                    />
                                )}
                                {cachedTokens > 0 && (
                                    <div
                                        style={{
                                            width: `${((cachedTokens || 0) / sumBuckets) * 100}%`,
                                            backgroundColor: TOKEN_BUCKET_COLORS.tokensCached
                                        }}
                                        title={`Cached: ${formatMetric("cachedTokens", cachedTokens)}`}
                                    />
                                )}
                                {outputTokens > 0 && (
                                    <div
                                        style={{
                                            width: `${((outputTokens || 0) / sumBuckets) * 100}%`,
                                            backgroundColor: TOKEN_BUCKET_COLORS.tokensOutput
                                        }}
                                        title={`Output: ${formatMetric("outputTokens", outputTokens)}`}
                                    />
                                )}
                            </div>
                        ) : (
                            <div className="progress-bar-fill h-full rounded-full" style={{ width: `${barPct}%`, backgroundColor: setup.color }} />
                        )}
                    </div>
                </div>
                {isTokens && (
                    <div className="flex items-center justify-end gap-1.5 sm:gap-2 text-[10px] text-slate-500 dark:text-slate-400 flex-wrap">
                        <span className="inline-flex items-center gap-1" title="Input tokens">
                            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: TOKEN_BUCKET_COLORS.tokensInput }} />
                            <span>{formatMetric("inputTokens", inputTokens)} in</span>
                        </span>
                        <span>·</span>
                        <span className="inline-flex items-center gap-1" title="Cached tokens">
                            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: TOKEN_BUCKET_COLORS.tokensCached }} />
                            <span>{formatMetric("cachedTokens", cachedTokens)} cached</span>
                        </span>
                        <span>·</span>
                        <span className="inline-flex items-center gap-1" title="Output tokens">
                            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: TOKEN_BUCKET_COLORS.tokensOutput }} />
                            <span>{formatMetric("outputTokens", outputTokens)} out</span>
                        </span>
                    </div>
                )}
            </div>

            {/* View-details affordance */}
            <div className="absolute right-6 top-5 sm:relative sm:right-auto sm:top-auto col-span-1 sm:col-span-1 flex items-center justify-end">
                <svg aria-hidden="true" className="w-4 h-4 text-slate-300 dark:text-slate-600 group-hover:text-indigo-500 dark:group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
                </svg>
            </div>
        </Link>
    );
}
