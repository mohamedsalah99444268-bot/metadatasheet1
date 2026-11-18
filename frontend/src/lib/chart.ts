import { useTheme } from "./theme";

export interface ChartColors {
  blue: string; cyan: string; green: string; red: string; amber: string; violet: string; slate: string;
  grid: string; axis: string; tooltipBg: string; tooltipBorder: string; text: string; series: string[];
}

const DARK: ChartColors = {
  blue: "#4C8DF6", cyan: "#22C7E0", green: "#34C38F", red: "#F06272", amber: "#E8B04B", violet: "#9D8CF2", slate: "#6B7480",
  grid: "#1F242C", axis: "#7C8593", tooltipBg: "#14171C", tooltipBorder: "#2A3039", text: "#E9EDF2",
  series: ["#4C8DF6", "#22C7E0", "#9D8CF2", "#34C38F", "#E8B04B", "#F06272", "#6B7480"],
};
const LIGHT: ChartColors = {
  blue: "#2563EB", cyan: "#0891B2", green: "#14915F", red: "#D23C4F", amber: "#B7791F", violet: "#6D5BD0", slate: "#8A93A0",
  grid: "#E6E9EE", axis: "#5D6673", tooltipBg: "#FFFFFF", tooltipBorder: "#DADFE6", text: "#12161C",
  series: ["#2563EB", "#0891B2", "#6D5BD0", "#14915F", "#B7791F", "#D23C4F", "#8A93A0"],
};

export function useChartColors(): ChartColors {
  const { theme } = useTheme();
  return theme === "light" ? LIGHT : DARK;
}

export function tooltipStyle(c: ChartColors) {
  return {
    contentStyle: { background: c.tooltipBg, border: `1px solid ${c.tooltipBorder}`, borderRadius: 8, fontSize: 12, color: c.text, boxShadow: "0 8px 24px rgba(0,0,0,.25)" },
    labelStyle: { color: c.axis, marginBottom: 4 },
    itemStyle: { color: c.text, padding: 0 },
    cursor: { fill: c.grid, opacity: 0.6 },
  };
}
