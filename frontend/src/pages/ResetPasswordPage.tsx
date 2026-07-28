import { useState, type FormEvent } from "react";
import { Link as RouterLink, useSearchParams } from "react-router-dom";
import { Alert, Button, Link, Stack, TextField, Typography } from "@mui/material";
import { authApi } from "@/services/authApi";
import { ErrorAlert } from "@/components/ErrorAlert";

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [succeeded, setSucceeded] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await authApi.resetPassword(token, newPassword, confirmNewPassword);
      setSucceeded(true);
    } catch (err) {
      setError(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!token) {
    return <Alert severity="error">This reset link is missing a token.</Alert>;
  }

  if (succeeded) {
    return (
      <Stack spacing={2}>
        <Alert severity="success">Your password has been reset successfully.</Alert>
        <Typography variant="body2" textAlign="center">
          <Link component={RouterLink} to="/login">
            Log in with your new password
          </Link>
        </Typography>
      </Stack>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <Stack spacing={2}>
        <ErrorAlert error={error} />
        <TextField
          label="New password"
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          helperText="At least 8 characters, with upper/lowercase and a digit"
          autoFocus
          required
          fullWidth
        />
        <TextField
          label="Confirm new password"
          type="password"
          value={confirmNewPassword}
          onChange={(e) => setConfirmNewPassword(e.target.value)}
          required
          fullWidth
        />
        <Button type="submit" variant="contained" size="large" loading={isSubmitting} fullWidth>
          Reset password
        </Button>
      </Stack>
    </form>
  );
}
