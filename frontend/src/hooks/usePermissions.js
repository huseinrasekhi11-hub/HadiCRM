import { useMemo } from "react";
import { useAuth } from "../context/AuthContext";
import * as perms from "../permissions";

export function usePermissions() {
  const { user } = useAuth();
  const role = user?.role;
  const userId = user?.id;

  return useMemo(() => {
    const isOwner = (leadOwnerId) => leadOwnerId === userId;
    return {
      role,
      userId,
      isOwner,
      canViewAllLeads: perms.canViewAllLeads(role),
      canAssignAnyLead: perms.canAssignAnyLead(role),
      isAdmin: perms.isAdminOnly(role),
      canModifyLead: (leadOwnerId) => perms.canModifyLead(role, isOwner(leadOwnerId)),
      canDeleteLead: (leadOwnerId) => perms.canModifyLead(role, isOwner(leadOwnerId)),
      roleLabel: perms.ROLE_LABELS[role] || role,
    };
  }, [role, userId]);
}
