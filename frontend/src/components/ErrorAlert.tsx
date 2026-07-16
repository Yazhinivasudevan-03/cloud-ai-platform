import { Alert } from "@mui/material";
import { extractErrorMessage } from "@/services/httpClient";

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <Alert severity="error" sx={{ mb: 2 }}>
      {extractErrorMessage(error)}
    </Alert>
  );
}
