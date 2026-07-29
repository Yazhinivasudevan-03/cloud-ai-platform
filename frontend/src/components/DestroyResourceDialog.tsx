import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import type { CloudResource, ProvisionableResourceType } from "@/types";

export function DestroyResourceDialog({
  open,
  accountId,
  resourceType,
  resource,
  onClose,
}: {
  open: boolean;
  accountId: number;
  resourceType: ProvisionableResourceType;
  resource: CloudResource | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [confirmText, setConfirmText] = useState("");

  const mutation = useMutation({
    mutationFn: () => {
      if (!resource) return Promise.reject(new Error("No resource selected"));
      return cloudProviderAccountsApi.destroyResource(accountId, resourceType, resource.id, {
        region: resource.region,
        confirm: confirmText,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts", accountId, "resources"] });
      setConfirmText("");
      onClose();
    },
  });

  const handleClose = () => {
    setConfirmText("");
    mutation.reset();
    onClose();
  };

  if (!resource) return null;

  const canSubmit = confirmText === resource.id;

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Destroy resource</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="error">
            This action is irreversible. It permanently deletes "{resource.name}" from the connected cloud
            provider account.
          </Alert>
          <ErrorAlert error={mutation.error} />

          <Typography variant="body2">
            Type the resource ID <strong>{resource.id}</strong> below to confirm.
          </Typography>

          <TextField
            label="Resource ID"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={resource.id}
            autoFocus
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Cancel</Button>
        <Button
          color="error"
          variant="contained"
          disabled={!canSubmit}
          loading={mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          Destroy
        </Button>
      </DialogActions>
    </Dialog>
  );
}
