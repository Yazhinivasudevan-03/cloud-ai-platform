import { ArcElement, Chart as ChartJS, Legend, Tooltip } from "chart.js";

/** Registers the Chart.js building blocks the app actually uses (a doughnut
 * chart on the Alerts page - see AlertsPage.tsx). Chart.js requires explicit
 * registration of each element/plugin it renders; importing this once at
 * app startup keeps that registration in one place instead of repeating it
 * in every component that renders a chart. */
ChartJS.register(ArcElement, Tooltip, Legend);
