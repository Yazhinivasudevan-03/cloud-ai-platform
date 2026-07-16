import { Outlet } from "react-router-dom";
import { Box, Paper, Stack, Typography } from "@mui/material";
import CloudQueueIcon from "@mui/icons-material/CloudQueue";

/** Centered-card shell for the login/register pages - deliberately has no
 * sidebar/topbar, since an unauthenticated visitor has nothing to navigate
 * to yet. */
export function AuthLayout() {
  return (
    <Box
      minHeight="100vh"
      display="flex"
      alignItems="center"
      justifyContent="center"
      sx={{ bgcolor: "background.default", px: 2 }}
    >
      <Paper sx={{ p: 4, width: "100%", maxWidth: 420 }}>
        <Stack spacing={1} alignItems="center" sx={{ mb: 3 }}>
          <CloudQueueIcon color="primary" sx={{ fontSize: 40 }} />
          <Typography variant="h5" textAlign="center">
            Cloud AI Platform
          </Typography>
          <Typography variant="body2" color="text.secondary" textAlign="center">
            Cloud usage monitoring &amp; AI-driven resource optimization
          </Typography>
        </Stack>
        <Outlet />
      </Paper>
    </Box>
  );
}
