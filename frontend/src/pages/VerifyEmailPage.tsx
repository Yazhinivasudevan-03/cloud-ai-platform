import { useEffect, useState } from "react";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import { Alert, Button, CircularProgress, Stack, Typography } from "@mui/material";
import { authApi } from "@/services/authApi";

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("This verification link is missing a token.");
      return;
    }
    let cancelled = false;
    authApi
      .verifyEmail(token)
      .then((result) => {
        if (cancelled) return;
        setStatus("success");
        setMessage(result.message);
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus("error");
        setMessage(
          err?.response?.data?.error?.message ?? "This verification link is invalid or has expired.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <Stack spacing={2} alignItems="center" textAlign="center">
      {status === "pending" && <CircularProgress size={32} />}
      {status === "success" && <Alert severity="success" sx={{ width: "100%" }}>{message}</Alert>}
      {status === "error" && <Alert severity="error" sx={{ width: "100%" }}>{message}</Alert>}
      {status !== "pending" && (
        <Typography variant="body2">
          <Button component={RouterLink} to="/login" variant="contained">
            Go to log in
          </Button>
        </Typography>
      )}
    </Stack>
  );
}
