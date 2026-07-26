import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Badge,
  Box,
  Button,
  Chip,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Popover,
  Stack,
  Typography,
} from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import NotificationsIcon from "@mui/icons-material/Notifications";
import { StatusChip } from "@/components/StatusChip";
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
  const summaryQuery = useQuery({
    queryKey: ["notifications", "summary"],
    queryFn: () => notificationsApi.summary(),
    refetchInterval: 30_000,
  });

  const unreadCount = summaryQuery.data?.unread_total ?? data?.meta.total ?? 0;

  const handleOpen = (event: React.MouseEvent<HTMLElement>) => setAnchorEl(event.currentTarget);
  const handleClose = () => setAnchorEl(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });

  const handleMarkRead = async (event: React.MouseEvent, notificationId: number) => {
    event.stopPropagation();
    await notificationsApi.markRead(notificationId);
    await invalidate();
  };

  const handleClear = async (event: React.MouseEvent, notificationId: number) => {
    event.stopPropagation();
    await notificationsApi.remove(notificationId);
    await invalidate();
  };

  const handleViewDetails = async (notificationId: number) => {
    await notificationsApi.markRead(notificationId);
    await invalidate();
    handleClose();
    navigate("/alerts");
  };

  const handleViewAll = () => {
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
        <Box sx={{ width: 380 }}>
          <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
            <Typography variant="subtitle2" gutterBottom>
              Unread notifications
            </Typography>
            {summaryQuery.data && (
              <Stack direction="row" spacing={1}>
                <Chip size="small" color="error" variant="outlined" label={`Critical ${summaryQuery.data.critical_count}`} />
                <Chip size="small" color="warning" variant="outlined" label={`Warning ${summaryQuery.data.warning_count}`} />
                <Chip size="small" color="default" variant="outlined" label={`Info ${summaryQuery.data.info_count}`} />
              </Stack>
            )}
          </Box>
          <Divider />
          {(!data || data.items.length === 0) && (
            <Typography variant="body2" color="text.secondary" sx={{ px: 2, py: 2 }}>
              You're all caught up.
            </Typography>
          )}
          <List dense disablePadding sx={{ maxHeight: 420, overflowY: "auto" }}>
            {data?.items.map((notification) => (
              <ListItemButton
                key={notification.id}
                onClick={() => handleViewDetails(notification.id)}
                sx={{ alignItems: "flex-start", flexDirection: "column", gap: 0.5 }}
              >
                <Stack direction="row" spacing={1} alignItems="center" sx={{ width: "100%" }}>
                  {notification.severity && <StatusChip value={notification.severity} />}
                  <Typography variant="caption" color="text.secondary">
                    {formatRelativeTime(notification.created_at)}
                  </Typography>
                  <Box sx={{ flexGrow: 1 }} />
                  <IconButton
                    size="small"
                    aria-label="Mark as read"
                    onClick={(e) => handleMarkRead(e, notification.id)}
                  >
                    <CheckIcon fontSize="inherit" />
                  </IconButton>
                  <IconButton
                    size="small"
                    aria-label="Clear notification"
                    onClick={(e) => handleClear(e, notification.id)}
                  >
                    <CloseIcon fontSize="inherit" />
                  </IconButton>
                </Stack>
                <ListItemText
                  primary={notification.message}
                  secondary={[notification.provider, notification.region, notification.resource]
                    .filter(Boolean)
                    .join(" - ") || notification.channel}
                  slotProps={{
                    primary: { variant: "body2" },
                    secondary: { variant: "caption" },
                  }}
                  sx={{ m: 0 }}
                />
              </ListItemButton>
            ))}
          </List>
          <Divider />
          <Box sx={{ p: 1 }}>
            <Button fullWidth size="small" onClick={handleViewAll}>
              View all notifications
            </Button>
          </Box>
        </Box>
      </Popover>
    </>
  );
}
