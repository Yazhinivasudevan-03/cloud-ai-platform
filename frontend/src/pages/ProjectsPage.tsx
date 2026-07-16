import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Stack, TextField, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/DeleteOutline";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ErrorAlert } from "@/components/ErrorAlert";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useAuth } from "@/contexts/AuthContext";
import { projectsApi } from "@/services/projectsApi";
import { formatDateTime } from "@/utils/formatters";
import type { Project } from "@/types";

export function ProjectsPage() {
  const navigate = useNavigate();
  const { hasRole } = useAuth();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search);
  const [createOpen, setCreateOpen] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState<Project | null>(null);

  const projectsQuery = useQuery({
    queryKey: ["projects", page, pageSize, debouncedSearch],
    queryFn: () => projectsApi.list({ page, pageSize, name: debouncedSearch }),
  });

  const deleteMutation = useMutation({
    mutationFn: (projectId: number) => projectsApi.remove(projectId),
    onSuccess: () => {
      setProjectToDelete(null);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const columns: DataTableColumn<Project>[] = [
    {
      header: "Name",
      render: (project) => (
        <Typography
          variant="body2"
          fontWeight={600}
          sx={{ cursor: "pointer" }}
          onClick={() => navigate(`/projects/${project.id}`)}
        >
          {project.name}
        </Typography>
      ),
    },
    { header: "Description", render: (project) => project.description || "-" },
    { header: "Created", render: (project) => formatDateTime(project.created_at) },
  ];

  if (hasRole("admin")) {
    columns.push({
      header: "",
      align: "right",
      render: (project) => (
        <IconButton size="small" onClick={() => setProjectToDelete(project)} aria-label="Delete project">
          <DeleteIcon fontSize="small" />
        </IconButton>
      ),
    });
  }

  return (
    <>
      <PageHeader
        title="Projects"
        subtitle="Top-level groupings of microservices, deployments, and cloud spend."
        actions={
          hasRole("operator", "admin") && (
            <Button startIcon={<AddIcon />} variant="contained" onClick={() => setCreateOpen(true)}>
              New project
            </Button>
          )
        }
      />
      <ErrorAlert error={projectsQuery.error} />
      <DataTable
        columns={columns}
        rows={projectsQuery.data?.items ?? []}
        total={projectsQuery.data?.meta.total ?? 0}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        isLoading={projectsQuery.isLoading}
        searchValue={search}
        onSearchChange={(value) => {
          setSearch(value);
          setPage(1);
        }}
        searchPlaceholder="Search projects by name..."
        emptyMessage="No projects yet. Create one to get started."
      />

      <CreateProjectDialog open={createOpen} onClose={() => setCreateOpen(false)} />

      <ConfirmDialog
        open={projectToDelete !== null}
        title="Delete project"
        description={`Delete "${projectToDelete?.name}"? This also deletes every microservice, deployment, and pod underneath it. This cannot be undone.`}
        confirmLabel="Delete"
        destructive
        onCancel={() => setProjectToDelete(null)}
        onConfirm={() => projectToDelete && deleteMutation.mutate(projectToDelete.id)}
      />
    </>
  );
}

function CreateProjectDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const queryClient = useQueryClient();

  const createMutation = useMutation({
    mutationFn: () => projectsApi.create({ name, description: description || undefined }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      setName("");
      setDescription("");
      onClose();
    },
  });

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>New project</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <ErrorAlert error={createMutation.error} />
          <TextField
            label="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            required
            fullWidth
          />
          <TextField
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            multiline
            rows={3}
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!name.trim()}
          loading={createMutation.isPending}
          onClick={() => createMutation.mutate()}
        >
          Create
        </Button>
      </DialogActions>
    </Dialog>
  );
}
