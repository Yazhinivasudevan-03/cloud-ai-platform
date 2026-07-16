import { useState, type FormEvent } from "react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { Button, Link, Stack, TextField, Typography } from "@mui/material";
import { useAuth } from "@/contexts/AuthContext";
import { ErrorAlert } from "@/components/ErrorAlert";

export function RegisterPage() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await register({ username, email, full_name: fullName || undefined, password });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Stack spacing={2}>
        <ErrorAlert error={error} />
        <TextField
          label="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          helperText="Letters, numbers, dots, underscores, hyphens only"
          autoFocus
          required
          fullWidth
        />
        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          fullWidth
        />
        <TextField
          label="Full name (optional)"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          fullWidth
        />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          helperText="At least 8 characters, with upper/lowercase and a digit"
          required
          fullWidth
        />
        <Button type="submit" variant="contained" size="large" loading={isSubmitting} fullWidth>
          Create account
        </Button>
        <Typography variant="body2" textAlign="center">
          Already have an account? <Link component={RouterLink} to="/login">Log in</Link>
        </Typography>
        <Typography variant="caption" color="text.secondary" textAlign="center">
          New accounts get the read-only "viewer" role automatically. Ask an
          admin to grant "operator" or "admin" for write access.
        </Typography>
      </Stack>
    </form>
  );
}
