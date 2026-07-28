import { useState, type FormEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import { Alert, Button, Link, Stack, TextField, Typography } from "@mui/material";
import { useAuth } from "@/contexts/AuthContext";
import { ErrorAlert } from "@/components/ErrorAlert";
import type { RegisterResponse } from "@/types";

export function RegisterPage() {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [mobileNumber, setMobileNumber] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [country, setCountry] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [registered, setRegistered] = useState<RegisterResponse | null>(null);
  const { register } = useAuth();

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const response = await register({
        first_name: firstName,
        last_name: lastName,
        email,
        mobile_number: mobileNumber,
        company_name: companyName || undefined,
        country,
        password,
        confirm_password: confirmPassword,
      });
      setRegistered(response);
    } catch (err) {
      setError(err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (registered) {
    return (
      <Stack spacing={2}>
        <Alert severity="success">Account created! Check your email to verify your address.</Alert>
        <Typography variant="body2" color="text.secondary">
          Email delivery isn't configured in this environment, so we can't send a real email yet -
          your verification link is shown below instead.
        </Typography>
        <Button
          component={RouterLink}
          to={`/verify-email?token=${encodeURIComponent(registered.verification_token)}`}
          variant="contained"
          fullWidth
        >
          Verify my email
        </Button>
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
        <Stack direction="row" spacing={2}>
          <TextField
            label="First name"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            autoFocus
            required
            fullWidth
          />
          <TextField
            label="Last name"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            required
            fullWidth
          />
        </Stack>
        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          fullWidth
        />
        <TextField
          label="Phone number"
          value={mobileNumber}
          onChange={(e) => setMobileNumber(e.target.value)}
          placeholder="+14155552671"
          helperText="E.164 format, e.g. +14155552671"
          required
          fullWidth
        />
        <TextField
          label="Company name (optional)"
          value={companyName}
          onChange={(e) => setCompanyName(e.target.value)}
          fullWidth
        />
        <TextField
          label="Country"
          value={country}
          onChange={(e) => setCountry(e.target.value)}
          required
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
        <TextField
          label="Confirm password"
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          required
          fullWidth
        />
        <Button type="submit" variant="contained" size="large" loading={isSubmitting} fullWidth>
          Create account
        </Button>
        <Typography variant="body2" textAlign="center">
          Already have an account? <Link component={RouterLink} to="/login">Log in</Link>
        </Typography>
      </Stack>
    </form>
  );
}
