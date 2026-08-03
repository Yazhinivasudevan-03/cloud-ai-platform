import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { PageHeader } from "@/components/PageHeader";
import { DataTable, type DataTableColumn } from "@/components/DataTable";
import { StatusChip } from "@/components/StatusChip";
import { notificationsApi } from "@/services/notificationsApi";
import { formatDateTime } from "@/utils/formatters";
import type { Notification } from "@/types";

const READ_OPTIONS = [
  { label: "All", value: "" },
  { label: "Unread", value: "false" },
  { label: "Read", value: "true" },
];

export function NotificationsPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  // Supports being linked to directly with a pre-applied filter, e.g. the
  // Dashboard's "Unread notifications" stat card links to
  // /notifications?filter=unread.
  const [readFilter, setReadFilter] = useState(searchParams.get("filter") === "unread" ? "false" : "");

  const query = useQuery({
    queryKey: ["notifications", "page", page, pageSize, readFilter],
    queryFn: () => notificationsApi.listMine(page, pageSize, readFilter === "" ? undefined : readFilter === "true"),
  });

  const markReadMutation = useMutation({
    mutationFn: (id: number) => notificationsApi.markRead(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const clearMutation = useMutation({
    mutationFn: (id: number) => notificationsApi.remove(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const columns: DataTableColumn<Notification>[] = [
    { header: "Received", render: (n) => formatDateTime(n.created_at) },
    { header: "Severity", render: (n) => (n.severity ? <StatusChip value={n.severity} /> : "-") },
    {
      header: "Cloud / Region / Resource",
      render: (n) => [n.provider, n.region, n.resource].filter(Boolean).join(" / ") || "-",
    },
    { header: "Channel", render: (n) => n.channel },
    { header: "Message", render: (n) => <Typography variant="body2">{n.message}</Typography> },
    {
      header: "SMS Delivery",
      render: (n) =>
        n.channel === "sms" ? (
          <Stack spacing={0.25}>
            <Typography variant="caption" color="text.secondary">
              {n.phone_number ?? "-"}
            </Typography>
            <StatusChip value={n.delivery_status ?? "unknown"} />
          </Stack>
        ) : (
          "-"
        ),
    },
    {
      header: "",
      align: "right",
      render: (n) => (
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          {!n.is_read && (
            <Button size="small" onClick={() => markReadMutation.mutate(n.id)}>
              Mark read
            </Button>
          )}
          <Button size="small" color="error" onClick={() => clearMutation.mutate(n.id)}>
            Clear
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <>
      <PageHeader title="Notifications" subtitle="Your personal notification inbox, across every alert channel." />
      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          label="Filter"
          value={readFilter}
          onChange={(e) => {
            setReadFilter(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 160 }}
        >
          {READ_OPTIONS.map((o) => (
            <MenuItem key={o.value} value={o.value}>
              {o.label}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
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
        emptyMessage="No notifications yet."
      />
    </>
  );
}
