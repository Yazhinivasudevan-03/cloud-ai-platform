import { useNavigate } from "react-router-dom";
import { IconButton, Tooltip } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

// Phase 23: a consistent Back button for every major page. Uses the
// existing React Router history stack (navigate(-1)) rather than a fixed
// "back to X" route, so filters/search params/pagination/selected cloud
// account/dashboard state on the previous page are preserved exactly as
// they were - popping history restores that page's own URL and component
// state, rather than a fresh navigation that would reset them. A safe
// no-op when there is no previous entry (e.g. a freshly opened tab).
export function BackButton() {
  const navigate = useNavigate();
  return (
    <Tooltip title="Back">
      <IconButton
        aria-label="Back"
        size="small"
        onClick={() => navigate(-1)}
        sx={{ mr: 1 }}
      >
        <ArrowBackIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
}
