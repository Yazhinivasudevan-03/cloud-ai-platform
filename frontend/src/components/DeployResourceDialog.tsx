import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import { ErrorAlert } from "@/components/ErrorAlert";
import { cloudProviderAccountsApi } from "@/services/cloudProviderAccountsApi";
import type { CloudRegion, ProvisionableResourceType } from "@/types";
import { PROVISIONABLE_RESOURCE_TYPES } from "@/types";

const RESOURCE_TYPE_LABELS: Record<ProvisionableResourceType, string> = {
  compute: "Compute instance",
  storage: "Storage bucket",
  networking: "Network (VPC)",
};

// Every provider's compute deploy() is hard-capped to one fixed,
// smallest/free-tier-eligible instance size in this pass (Phase 25D) - not
// user-configurable here, to bound real-world cost/blast-radius risk.
const SPEC_HELP: Record<ProvisionableResourceType, string> = {
  compute:
    "Depending on the connected provider, additional fields may be required: image_id (AWS/OCI/Alibaba), " +
    "resource_group / subnet_id / admin_username / admin_password (Azure), availability_domain (OCI), " +
    "security_group_id (Alibaba). Instance size is fixed to the smallest free-tier-eligible option.",
  storage: "Azure requires an additional resource_group field. Other providers need only the name below.",
  networking: "Azure requires an additional resource_group field; a cidr_block may optionally be set (default 10.0.0.0/16).",
};

interface SpecField {
  key: string;
  value: string;
}

export function DeployResourceDialog({
  open,
  accountId,
  regions,
  defaultRegion,
  onClose,
}: {
  open: boolean;
  accountId: number;
  regions: CloudRegion[];
  defaultRegion: string;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();

  const [resourceType, setResourceType] = useState<ProvisionableResourceType>("compute");
  const [region, setRegion] = useState(defaultRegion);
  const [name, setName] = useState("");
  const [specFields, setSpecFields] = useState<SpecField[]>([]);

  const mutation = useMutation({
    mutationFn: () => {
      const spec: Record<string, string> = { name: name.trim() };
      for (const field of specFields) {
        if (field.key.trim()) spec[field.key.trim()] = field.value;
      }
      return cloudProviderAccountsApi.deployResource(accountId, { resource_type: resourceType, region, spec });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["cloud-provider-accounts", accountId, "resources"] });
      setName("");
      setSpecFields([]);
      onClose();
    },
  });

  const canSubmit = name.trim() !== "" && region.trim() !== "";

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Deploy resource</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="warning">
            This performs a real create call against the connected cloud provider account and may incur
            provider charges.
          </Alert>
          <ErrorAlert error={mutation.error} />

          <TextField
            select
            label="Resource type"
            value={resourceType}
            onChange={(e) => setResourceType(e.target.value as ProvisionableResourceType)}
            fullWidth
          >
            {PROVISIONABLE_RESOURCE_TYPES.map((type) => (
              <MenuItem key={type} value={type}>
                {RESOURCE_TYPE_LABELS[type]}
              </MenuItem>
            ))}
          </TextField>

          <TextField select label="Region" value={region} onChange={(e) => setRegion(e.target.value)} fullWidth required>
            {regions.map((r) => (
              <MenuItem key={r.id} value={r.id}>
                {r.display_name}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            label="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. my-test-instance"
            required
            fullWidth
            autoFocus
          />

          <Typography variant="caption" color="text.secondary">
            {SPEC_HELP[resourceType]}
          </Typography>

          <Stack spacing={1}>
            {specFields.map((field, index) => (
              <Stack key={index} direction="row" spacing={1} alignItems="center">
                <TextField
                  label="Field name"
                  size="small"
                  value={field.key}
                  onChange={(e) =>
                    setSpecFields((prev) => prev.map((f, i) => (i === index ? { ...f, key: e.target.value } : f)))
                  }
                  sx={{ flex: 1 }}
                />
                <TextField
                  label="Value"
                  size="small"
                  value={field.value}
                  onChange={(e) =>
                    setSpecFields((prev) => prev.map((f, i) => (i === index ? { ...f, value: e.target.value } : f)))
                  }
                  sx={{ flex: 1 }}
                />
                <IconButton
                  size="small"
                  aria-label="Remove field"
                  onClick={() => setSpecFields((prev) => prev.filter((_, i) => i !== index))}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Stack>
            ))}
            <Button
              size="small"
              startIcon={<AddIcon />}
              onClick={() => setSpecFields((prev) => [...prev, { key: "", value: "" }])}
              sx={{ alignSelf: "flex-start" }}
            >
              Add field
            </Button>
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!canSubmit} loading={mutation.isPending} onClick={() => mutation.mutate()}>
          Deploy
        </Button>
      </DialogActions>
    </Dialog>
  );
}
