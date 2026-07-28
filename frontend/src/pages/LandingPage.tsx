import { Navigate, Link as RouterLink } from "react-router-dom";
import { Box, Button, Container, Paper, Stack, Typography } from "@mui/material";
import Grid from "@mui/material/Grid2";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import AutoGraphOutlinedIcon from "@mui/icons-material/AutoGraphOutlined";
import NotificationsActiveOutlinedIcon from "@mui/icons-material/NotificationsActiveOutlined";
import SavingsOutlinedIcon from "@mui/icons-material/SavingsOutlined";
import CloudQueueOutlinedIcon from "@mui/icons-material/CloudQueueOutlined";
import SecurityOutlinedIcon from "@mui/icons-material/SecurityOutlined";
import { useAuth } from "@/contexts/AuthContext";

const FEATURES = [
  {
    icon: MonitorHeartOutlinedIcon,
    title: "Real-time monitoring",
    description:
      "Live CPU, memory, disk and network usage for every deployment, pulled straight from AWS " +
      "CloudWatch, Azure Monitor, Google Cloud Monitoring, and Prometheus/Kubernetes - no synthetic " +
      "or placeholder data.",
  },
  {
    icon: AutoGraphOutlinedIcon,
    title: "AI-driven predictions",
    description:
      "LSTM workload forecasting, Isolation Forest anomaly detection, and Random Forest failure " +
      "prediction turn your usage history into an early warning system, not just a dashboard.",
  },
  {
    icon: NotificationsActiveOutlinedIcon,
    title: "Real-time alerts",
    description:
      "Threshold-based alerts across CPU, memory, disk, network, cost, and security reach you " +
      "instantly by email, SMS, Slack, Telegram, or Microsoft Teams - configurable per category.",
  },
  {
    icon: SavingsOutlinedIcon,
    title: "Cost optimization",
    description:
      "Actionable, prediction-informed recommendations to right-size deployments and cut cloud " +
      "spend, backed by real billing data from Cost Explorer and Cost Management.",
  },
  {
    icon: CloudQueueOutlinedIcon,
    title: "Multi-cloud, multi-account",
    description:
      "Connect AWS, Azure, Google Cloud, Oracle Cloud, IBM Cloud, DigitalOcean, and Alibaba Cloud " +
      "accounts side by side - view them combined or switch between them at will.",
  },
  {
    icon: SecurityOutlinedIcon,
    title: "Built for your workspace alone",
    description:
      "Every account is fully isolated: your cloud accounts, monitoring data, alerts, predictions " +
      "and reports are visible only to you - never to another tenant on the platform.",
  },
];

export function LandingPage() {
  const { isAuthenticated } = useAuth();

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <>
      <Box sx={{ py: { xs: 8, md: 12 } }}>
        <Container maxWidth="md">
          <Stack spacing={3} alignItems="center" textAlign="center">
            <Typography variant="h2" fontWeight={700} sx={{ textWrap: "balance" }}>
              Cloud usage monitoring, driven by AI
            </Typography>
            <Typography variant="h6" color="text.secondary" fontWeight={400} sx={{ maxWidth: 640 }}>
              Connect your AWS, Azure, Google Cloud, or any other cloud account and get real-time
              monitoring, predictive resource optimization, and instant alerts - all in one place,
              scoped entirely to your own infrastructure.
            </Typography>
            <Stack direction="row" spacing={2} sx={{ pt: 1 }}>
              <Button component={RouterLink} to="/register" variant="contained" size="large">
                Get started free
              </Button>
              <Button component={RouterLink} to="/login" variant="outlined" size="large">
                Log in
              </Button>
            </Stack>
          </Stack>
        </Container>
      </Box>

      <Box id="features" sx={{ py: { xs: 6, md: 10 }, bgcolor: "background.paper" }}>
        <Container maxWidth="lg">
          <Typography variant="h4" fontWeight={700} textAlign="center" gutterBottom>
            Everything you need to run cloud infrastructure with confidence
          </Typography>
          <Grid container spacing={3} sx={{ mt: 2 }}>
            {FEATURES.map((feature) => (
              <Grid key={feature.title} size={{ xs: 12, sm: 6, md: 4 }}>
                <Paper sx={{ p: 3, height: "100%" }}>
                  <feature.icon color="primary" sx={{ fontSize: 32, mb: 1.5 }} />
                  <Typography variant="h6" gutterBottom>
                    {feature.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {feature.description}
                  </Typography>
                </Paper>
              </Grid>
            ))}
          </Grid>
        </Container>
      </Box>

      <Box id="about" sx={{ py: { xs: 6, md: 10 } }}>
        <Container maxWidth="md">
          <Typography variant="h4" fontWeight={700} gutterBottom>
            About
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Cloud AI Platform brings together cloud usage monitoring, AI-driven predictive analysis,
            and resource optimization in a single multi-tenant SaaS product. Each account you connect
            is monitored using the cloud provider's own official APIs, and every prediction, alert,
            and recommendation is generated from your real usage data - never fabricated or shared
            across accounts. Every user works in their own fully isolated workspace, with dashboards,
            alerts, notifications, and AI results scoped exclusively to the cloud accounts they've
            connected.
          </Typography>
        </Container>
      </Box>

      <Box id="contact" sx={{ py: { xs: 6, md: 10 }, bgcolor: "background.paper" }}>
        <Container maxWidth="md">
          <Typography variant="h4" fontWeight={700} gutterBottom>
            Contact
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Questions about connecting a cloud account, monitoring setup, or anything else?
            Reach us at{" "}
            <Typography component="a" href="mailto:support@cloud-ai-platform.example" color="primary">
              support@cloud-ai-platform.example
            </Typography>
            .
          </Typography>
        </Container>
      </Box>
    </>
  );
}
