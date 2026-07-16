import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Badge,
  Box,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Popover,
  Typography,
} from "@mui/material";
import NotificationsIcon from "@mui/icons-material/Notifications";
import { notificationsApi } from "@/services/notificationsApi";
import { formatRelativeTime } from "@/utils/formatters";

/** Polls unread notifications every 30s (a deliberate, honestly-simple
 * stand-in for real-time push - the backend has no WebSocket/SSE endpoint,
 * so polling is the "Real-time Updates" mechanism here; see docs/PHASE_7.md). */
export function NotificationBell() {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ["notifications", "unread-preview"],
    queryFn: () => notificationsApi.listMine(1, 5, false),
    refetchInterval: 30_000,
  });

  const unreadCount = data?.meta.total ?? 0;

  const handleOpen = (event: React.MouseEvent<HTMLElement>) => setAnchorEl(event.currentTarget);
  const handleClose = () => setAnchorEl(null);

  const handleSelect = async (notificationId: number) => {
    await notificationsApi.markRead(notificationId);
    await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    handleClose();
    navigate("/notifications");
  };

  return (
    <>
      <IconButton color="inherit" onClick={handleOpen} aria-label="Notifications">
        <Badge badgeContent={unreadCount} color="error">
          <NotificationsIcon />
        </Badge>
      </IconButton>
      <Popover
        open={Boolean(anchorEl)}
        anchorEl={anchorEl}
        onClose={handleClose}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
      >
        <Box sx={{ width: 340 }}>
          <Typography variant="subtitle2" sx={{ px: 2, pt: 1.5, pb: 0.5 }}>
            Unread notifications
          </Typography>
          {(!data || data.items.length === 0) && (
            <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 2 }}>
              You're all caught up.
            </Typography>
          )}
          <List dense disablePadding>
            {data?.items.map((notification) => (
              <ListItemButton
                key={notification.id}
                onClick={() => handleSelect(notification.id)}
                sx={{ alignItems: "flex-start" }}
              >
                <ListItemText
                  primary={notification.message}
                  secondary={`${notification.channel} - ${formatRelativeTime(notification.created_at)}`}
                  slotProps={{
                    primary: { variant: "body2" },
                    secondary: { variant: "caption" },
                  }}
                />
              </ListItemButton>
            ))}
          </List>
        </Box>
      </Popover>
    </>
  );
}
