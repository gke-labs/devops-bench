import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { MetricToggle } from "./MetricToggle.jsx";
import { METRICS, METRIC_LABELS, metricDescription, metricMeta, metricShortLabel } from "../lib/vocab.js";

const buttonFor = metric => screen.getByRole("button", { name: METRIC_LABELS[metric] });

// The pill a button sits in — the split that keeps eight metrics from
// overflowing the leaderboard's score column.
const groupOf = metric => buttonFor(metric).parentElement;

describe("MetricToggle", () => {
    it("renders a button for every metric in the vocab", () => {
        render(<MetricToggle value="composite" onChange={() => {}} />);
        // Guards the whole vocab, not a hardcoded list: adding a metric key
        // without a toggle button would leave it unreachable in the UI.
        expect(screen.getAllByRole("button")).toHaveLength(METRICS.length);
        for (const m of METRICS) expect(buttonFor(m)).toBeInTheDocument();
    });

    it("splits quality and efficiency metrics into separate groups", () => {
        render(<MetricToggle value="composite" onChange={() => {}} />);
        const quality = METRICS.filter(m => metricMeta(m).percentage);
        const efficiency = METRICS.filter(m => !metricMeta(m).percentage);

        // Every member of a family shares one pill, and the two pills differ —
        // so a wrap falls between the families rather than mid-strip.
        expect(new Set(quality.map(groupOf)).size).toBe(1);
        expect(new Set(efficiency.map(groupOf)).size).toBe(1);
        expect(groupOf(quality[0])).not.toBe(groupOf(efficiency[0]));
    });

    it("keeps METRICS order within each group", () => {
        render(<MetricToggle value="composite" onChange={() => {}} />);
        const rendered = screen.getAllByRole("button").map(b => b.textContent);
        const expected = [
            ...METRICS.filter(m => metricMeta(m).percentage),
            ...METRICS.filter(m => !metricMeta(m).percentage)
        ].map(metricShortLabel);
        expect(rendered).toEqual(expected);
    });

    it("abbreviates the visible text but keeps the full accessible name", () => {
        render(<MetricToggle value="composite" onChange={() => {}} />);
        // Shortening is a fit concern, not a vocabulary change: a screen reader
        // and every query below still address the metric by its real label.
        const button = buttonFor("recoverableSafety");
        expect(button).toHaveTextContent("Rec. Safety");
        expect(button).toHaveAccessibleName("Recoverable Safety");
    });

    it("marks the active metric and reports a click", () => {
        const onChange = vi.fn();
        render(<MetricToggle value="latency" onChange={onChange} />);
        expect(buttonFor("latency")).toHaveAttribute("aria-pressed", "true");
        expect(buttonFor("composite")).toHaveAttribute("aria-pressed", "false");

        fireEvent.click(buttonFor("outputTokens"));
        expect(onChange).toHaveBeenCalledWith("outputTokens");
    });

    it("disables metrics missing from `available` rather than hiding them", () => {
        const onChange = vi.fn();
        render(<MetricToggle value="composite" onChange={onChange} available={["composite", "latency"]} />);

        expect(buttonFor("pass5")).toBeDisabled();
        expect(buttonFor("latency")).toBeEnabled();
        fireEvent.click(buttonFor("pass5"));
        expect(onChange).not.toHaveBeenCalled();
    });

    it("enables every metric when `available` is omitted or empty", () => {
        render(<MetricToggle value="composite" onChange={() => {}} available={[]} />);
        for (const m of METRICS) expect(buttonFor(m)).toBeEnabled();
    });

    it("explains a disabled metric by the reason it is actually missing", () => {
        // One hardcoded sentence used to cover every disabled button, so a
        // harness that reports no timings put "Available once multi-iteration
        // runs land" under Latency, which has nothing to do with iterations.
        render(<MetricToggle value="composite" onChange={() => {}} available={["composite"]} />);
        expect(buttonFor("pass5")).toHaveAttribute("title", "Available once multi-iteration runs land");
        expect(buttonFor("latency")).toHaveAttribute("title", "Not reported by these runs");
        expect(buttonFor("outputTokens")).toHaveAttribute("title", "Not reported by these runs");
    });

    it("describes an enabled metric instead of explaining its absence", () => {
        render(<MetricToggle value="composite" onChange={() => {}} available={["composite", "latency"]} />);
        expect(buttonFor("latency")).toHaveAttribute("title", metricDescription("latency"));
    });
});
