import { Link as RouterLink } from "react-router-dom";
import { Box, Button, Stack, Typography } from "@mui/material";

export function NotFoundPage() {
  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
      <Stack spacing={2} alignItems="center">
        <Typography variant="h2" fontWeight={700}>
          404
        </Typography>
        <Typography variant="body1" color="text.secondary">
          This page doesn't exist.
        </Typography>
        <Button component={RouterLink} to="/" variant="contained">
          Back to dashboard
        </Button>
      </Stack>
    </Box>
  );
}
