import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  AppBar,
  Box,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import CloudQueueIcon from "@mui/icons-material/CloudQueue";
import DashboardIcon from "@mui/icons-material/DashboardOutlined";
import FolderIcon from "@mui/icons-material/FolderOutlined";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActiveOutlined";
import TuneIcon from "@mui/icons-material/TuneOutlined";
import MailIcon from "@mui/icons-material/MailOutlined";
import CloudSyncIcon from "@mui/icons-material/CloudSyncOutlined";
import PeopleIcon from "@mui/icons-material/PeopleOutlined";
import Brightness4Icon from "@mui/icons-material/Brightness4";
import Brightness7Icon from "@mui/icons-material/Brightness7";
import { useAuth } from "@/contexts/AuthContext";
import { useThemeMode } from "@/contexts/ThemeModeContext";
import { NotificationBell } from "@/components/NotificationBell";
import { UserMenu } from "@/components/UserMenu";

const DRAWER_WIDTH = 240;

const NAV_ITEMS = [
  { label: "Dashboard", to: "/", icon: <DashboardIcon /> },
  { label: "Projects", to: "/projects", icon: <FolderIcon /> },
  { label: "Alerts", to: "/alerts", icon: <NotificationsActiveIcon /> },
  { label: "Optimization", to: "/optimization", icon: <TuneIcon /> },
  { label: "Notifications", to: "/notifications", icon: <MailIcon /> },
  { label: "Cloud Accounts", to: "/cloud-accounts", icon: <CloudSyncIcon /> },
];

export function AppLayout() {
  const theme = useTheme();
  const isSmallScreen = useMediaQuery(theme.breakpoints.down("md"));
  const [mobileOpen, setMobileOpen] = useState(false);
  const { hasRole } = useAuth();
  const { mode, toggleMode } = useThemeMode();
  const location = useLocation();

  const navItems = hasRole("admin")
    ? [...NAV_ITEMS, { label: "Users", to: "/users", icon: <PeopleIcon /> }]
    : NAV_ITEMS;

  const drawerContent = (
    <Box>
      <Toolbar sx={{ gap: 1 }}>
        <CloudQueueIcon color="primary" />
        <Typography variant="subtitle1" fontWeight={700} noWrap>
          Cloud AI Platform
        </Typography>
      </Toolbar>
      <Divider />
      <List sx={{ px: 1, py: 1 }}>
        {navItems.map((item) => (
          <ListItemButton
            key={item.to}
            component={NavLink}
            to={item.to}
            end={item.to === "/"}
            selected={location.pathname === item.to}
            sx={{ borderRadius: 2, mb: 0.5 }}
            onClick={() => setMobileOpen(false)}
          >
            <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
            <ListItemText primary={item.label} />
          </ListItemButton>
        ))}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: "flex" }}>
      <AppBar
        position="fixed"
        color="default"
        elevation={0}
        sx={{
          zIndex: theme.zIndex.drawer + 1,
          borderBottom: `1px solid ${theme.palette.divider}`,
          bgcolor: "background.paper",
        }}
      >
        <Toolbar sx={{ gap: 1 }}>
          {isSmallScreen && (
            <IconButton edge="start" onClick={() => setMobileOpen(true)} aria-label="Open menu">
              <MenuIcon />
            </IconButton>
          )}
          <Box sx={{ flexGrow: 1 }} />
          <Tooltip title={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
            <IconButton onClick={toggleMode} color="inherit" aria-label="Toggle theme">
              {mode === "dark" ? <Brightness7Icon /> : <Brightness4Icon />}
            </IconButton>
          </Tooltip>
          <NotificationBell />
          <UserMenu />
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
        <Drawer
          variant={isSmallScreen ? "temporary" : "permanent"}
          open={isSmallScreen ? mobileOpen : true}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            "& .MuiDrawer-paper": {
              boxSizing: "border-box",
              width: DRAWER_WIDTH,
              borderRight: `1px solid ${theme.palette.divider}`,
            },
          }}
        >
          {drawerContent}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          minHeight: "100vh",
          bgcolor: "background.default",
        }}
      >
        <Toolbar />
        <Box sx={{ p: { xs: 2, sm: 3 } }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
