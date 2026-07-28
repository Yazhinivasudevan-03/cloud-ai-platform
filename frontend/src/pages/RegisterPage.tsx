import { useState, type ChangeEvent, type FormEvent } from "react";
import { Link as RouterLink } from "react-router-dom";
import { Alert, Button, Link, Stack, TextField, Typography } from "@mui/material";
import { useAuth } from "@/contexts/AuthContext";
import { ErrorAlert } from "@/components/ErrorAlert";
import { extractFieldErrors, FORM_ERROR_KEY } from "@/services/httpClient";
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
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [registered, setRegistered] = useState<RegisterResponse | null>(null);
  const { register } = useAuth();

  // Clears a single field's error as soon as the user edits it, rather
  // than leaving a stale message once they've started fixing it.
  const withFieldClear = (
    setter: (value: string) => void,
    field: string,
  ): ((event: ChangeEvent<HTMLInputElement>) => void) => (event) => {
    setter(event.target.value);
    setFieldErrors((prev) => {
      if (!(field in prev)) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
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
      const fe = extractFieldErrors(err);
      const namedFieldErrors = Object.keys(fe).filter((key) => key !== FORM_ERROR_KEY);
      setFieldErrors(fe);
      // Only show the generic banner when nothing could be mapped to a
      // specific input (e.g. a 409 "email already exists" conflict, or a
      // network failure) - a real per-field message is always preferred
      // over a duplicate top-level one.
      setError(namedFieldErrors.length > 0 ? null : err);
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
            onChange={withFieldClear(setFirstName, "first_name")}
            error={Boolean(fieldErrors.first_name)}
            helperText={fieldErrors.first_name}
            autoFocus
            required
            fullWidth
          />
          <TextField
            label="Last name"
            value={lastName}
            onChange={withFieldClear(setLastName, "last_name")}
            error={Boolean(fieldErrors.last_name)}
            helperText={fieldErrors.last_name}
            required
            fullWidth
          />
        </Stack>
        <TextField
          label="Email"
          type="email"
          value={email}
          onChange={withFieldClear(setEmail, "email")}
          error={Boolean(fieldErrors.email)}
          helperText={fieldErrors.email}
          required
          fullWidth
        />
        <TextField
          label="Phone number"
          value={mobileNumber}
          onChange={withFieldClear(setMobileNumber, "mobile_number")}
          placeholder="+14155552671"
          error={Boolean(fieldErrors.mobile_number)}
          helperText={fieldErrors.mobile_number ?? "E.164 format, e.g. +14155552671"}
          required
          fullWidth
        />
        <TextField
          label="Company name (optional)"
          value={companyName}
          onChange={withFieldClear(setCompanyName, "company_name")}
          error={Boolean(fieldErrors.company_name)}
          helperText={fieldErrors.company_name}
          fullWidth
        />
        <TextField
          label="Country"
          value={country}
          onChange={withFieldClear(setCountry, "country")}
          error={Boolean(fieldErrors.country)}
          helperText={fieldErrors.country}
          required
          fullWidth
        />
        <TextField
          label="Password"
          type="password"
          value={password}
          onChange={withFieldClear(setPassword, "password")}
          error={Boolean(fieldErrors.password)}
          helperText={fieldErrors.password ?? "At least 8 characters, with upper/lowercase and a digit"}
          required
          fullWidth
        />
        <TextField
          label="Confirm password"
          type="password"
          value={confirmPassword}
          onChange={withFieldClear(setConfirmPassword, "confirm_password")}
          error={Boolean(fieldErrors.confirm_password)}
          helperText={fieldErrors.confirm_password}
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
