import { Link as RouterLink } from "react-router-dom";
import { AppBar, Box, Button, Container, Stack, Toolbar, Typography } from "@mui/material";
import CloudQueueIcon from "@mui/icons-material/CloudQueue";
import { Outlet } from "react-router-dom";

/** Top nav + footer shell for the public, unauthenticated marketing pages
 * (Landing Page today) - distinct from AuthLayout's centered-card shell
 * (login/register forms) and AppLayout's authenticated sidebar. */
export function PublicLayout() {
  return (
    <Box sx={{ bgcolor: "background.default", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <AppBar
        position="sticky"
        color="default"
        elevation={0}
        sx={{ borderBottom: (theme) => `1px solid ${theme.palette.divider}`, bgcolor: "background.paper" }}
      >
        <Container maxWidth="lg">
          <Toolbar disableGutters sx={{ gap: 1 }}>
            <CloudQueueIcon color="primary" />
            <Typography variant="subtitle1" fontWeight={700} sx={{ mr: "auto" }}>
              Cloud AI Platform
            </Typography>
            <Stack direction="row" spacing={1} sx={{ display: { xs: "none", sm: "flex" } }}>
              <Button component="a" href="#features" color="inherit">
                Features
              </Button>
              <Button component="a" href="#about" color="inherit">
                About
              </Button>
              <Button component="a" href="#contact" color="inherit">
                Contact
              </Button>
            </Stack>
            <Button component={RouterLink} to="/login" color="inherit">
              Log in
            </Button>
            <Button component={RouterLink} to="/register" variant="contained">
              Sign up
            </Button>
          </Toolbar>
        </Container>
      </AppBar>

      <Box component="main" sx={{ flexGrow: 1 }}>
        <Outlet />
      </Box>

      <Box component="footer" sx={{ borderTop: (theme) => `1px solid ${theme.palette.divider}`, py: 3 }}>
        <Container maxWidth="lg">
          <Typography variant="body2" color="text.secondary" textAlign="center">
            &copy; {new Date().getFullYear()} Cloud AI Platform. Cloud usage monitoring &amp; AI-driven
            predictive resource optimization.
          </Typography>
        </Container>
      </Box>
    </Box>
  );
}
