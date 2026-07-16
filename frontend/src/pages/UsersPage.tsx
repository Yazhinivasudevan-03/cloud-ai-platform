import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Chip, MenuItem, Stack, TextField } from "@mui/material";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { ErrorAlert } from "@/components/ErrorAlert";
import { usersApi } from "@/services/usersApi";
import type { RoleName, User } from "@/types";

const ASSIGNABLE_ROLES: RoleName[] = ["viewer", "operator", "admin"];

export function UsersPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [error, setError] = useState<unknown>(null);

  const query = useQuery({
    queryKey: ["users", page, pageSize],
    queryFn: () => usersApi.list(page, pageSize),
  });

  const assignMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) => usersApi.assignRole(userId, role),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["users"] }),
    onError: setError,
  });

  const removeMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) => usersApi.removeRole(userId, role),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["users"] }),
    onError: setError,
  });

  const columns: DataTableColumn<User>[] = [
    { header: "Username", render: (u) => u.username },
    { header: "Email", render: (u) => u.email },
    {
      header: "Roles",
      render: (u) => (
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          {u.roles.map((role) => (
            <Chip
              key={role.id}
              label={role.name}
              size="small"
              onDelete={() => removeMutation.mutate({ userId: u.id, role: role.name })}
            />
          ))}
          {u.roles.length === 0 && <Chip label="no roles" size="small" variant="outlined" />}
        </Stack>
      ),
    },
    {
      header: "Grant role",
      render: (u) => (
        <TextField
          select
          size="small"
          value=""
          onChange={(e) => assignMutation.mutate({ userId: u.id, role: e.target.value })}
          sx={{ minWidth: 140 }}
          slotProps={{ select: { displayEmpty: true } }}
        >
          <MenuItem value="" disabled>
            Select role...
          </MenuItem>
          {ASSIGNABLE_ROLES.filter((role) => !u.roles.some((r) => r.name === role)).map((role) => (
            <MenuItem key={role} value={role}>
              {role}
            </MenuItem>
          ))}
        </TextField>
      ),
    },
  ];

  return (
    <>
      <PageHeader title="Users" subtitle="Admin: manage platform users and their roles." />
      <ErrorAlert error={error} />
      <DataTable
        columns={columns}
        rows={query.data?.items ?? []}
        total={query.data?.meta.total ?? 0}
        page={page}
        pageSize={pageSize}
        onPageChange={setPage}
        onPageSizeChange={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        isLoading={query.isLoading}
        emptyMessage="No users found."
      />
    </>
  );
}
