import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar, IconButton, ListItemIcon, Menu, MenuItem, Typography, Divider } from "@mui/material";
import SettingsIcon from "@mui/icons-material/Settings";
import NotificationsActiveIcon from "@mui/icons-material/NotificationsActive";
import PeopleIcon from "@mui/icons-material/PeopleOutlined";
import LogoutIcon from "@mui/icons-material/Logout";
import { useAuth } from "@/contexts/AuthContext";

export function UserMenu() {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const { user, logout, hasRole } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;

  const initials = (user.full_name || user.username).slice(0, 2).toUpperCase();

  return (
    <>
      <IconButton onClick={(e) => setAnchorEl(e.currentTarget)} aria-label="Account menu">
        <Avatar sx={{ width: 32, height: 32, fontSize: 14 }}>{initials}</Avatar>
      </IconButton>
      <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={() => setAnchorEl(null)}>
        <MenuItem disabled>
          <Typography variant="body2">
            {user.full_name || user.username}
            <br />
            <Typography component="span" variant="caption" color="text.secondary">
              {user.roles.map((r) => r.name).join(", ") || "no roles"}
            </Typography>
          </Typography>
        </MenuItem>
        <Divider />
        <MenuItem
          onClick={() => {
            setAnchorEl(null);
            navigate("/profile");
          }}
        >
          <ListItemIcon>
            <SettingsIcon fontSize="small" />
          </ListItemIcon>
          Profile
        </MenuItem>
        <MenuItem
          onClick={() => {
            setAnchorEl(null);
            navigate("/notification-settings");
          }}
        >
          <ListItemIcon>
            <NotificationsActiveIcon fontSize="small" />
          </ListItemIcon>
          Notification Settings
        </MenuItem>
        {hasRole("admin") && (
          <MenuItem
            onClick={() => {
              setAnchorEl(null);
              navigate("/users");
            }}
          >
            <ListItemIcon>
              <PeopleIcon fontSize="small" />
            </ListItemIcon>
            Manage Users
          </MenuItem>
        )}
        <Divider />
        <MenuItem
          onClick={() => {
            setAnchorEl(null);
            logout();
            navigate("/login");
          }}
        >
          <ListItemIcon>
            <LogoutIcon fontSize="small" />
          </ListItemIcon>
          Log out
        </MenuItem>
      </Menu>
    </>
  );
}
