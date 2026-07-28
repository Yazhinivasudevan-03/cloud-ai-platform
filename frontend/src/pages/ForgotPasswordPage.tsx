import { useState, type FormEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import { Alert, Button, Link, Stack, TextField, Typography } from "@mui/material";
import { authApi } from "@/services/authApi";
import { ErrorAlert } from "@/components/ErrorAlert";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await authApi.forgotPassword(email);
      setSubmitted(true);
    } catch (err) {
      setError(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <Stack spacing={2}>
        <Alert severity="success">
          If an account with that email exists, a password reset link has been sent.
        </Alert>
        <Typography variant="body2" textAlign="center">
          <Link component={RouterLink} to="/login">
            Back to log in
          </Link>
        </Typography>
      </Stack>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <Stack spacing={2}>
        <ErrorAlert error={error} />
        <Typography variant="body2" color="text.secondary">
          Enter the email address on your account and we'll send you a link to reset your password.
        </Typography>
        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoFocus
          required
          fullWidth
        />
        <Button type="submit" variant="contained" size="large" loading={isSubmitting} fullWidth>
          Send reset link
        </Button>
        <Typography variant="body2" textAlign="center">
          <Link component={RouterLink} to="/login">
            Back to log in
          </Link>
        </Typography>
      </Stack>
    </form>
  );
}
