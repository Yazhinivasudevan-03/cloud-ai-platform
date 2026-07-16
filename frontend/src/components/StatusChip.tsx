import { Chip } from "@mui/material";
import { statusColor } from "@/utils/statusColors";
import { titleCase } from "@/utils/formatters";

export function StatusChip({ value }: { value: string }) {
  return <Chip label={titleCase(value)} color={statusColor(value)} size="small" variant="outlined" />;
}
