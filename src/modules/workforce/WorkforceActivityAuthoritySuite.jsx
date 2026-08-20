import React, { useEffect, useState } from "react";

import { useAuth } from "../../auth/AuthContext.jsx";
import WorkforceActivityStudio from "./WorkforceActivityStudio.jsx";
import WorkforceDemandProof from "./WorkforceDemandProof.jsx";
import {
  loadWorkforceFlexibilityAdmin,
  loadWorkforceLaborStandards,
} from "./workforceFlexibilityApi.js";


export default function WorkforceActivityAuthoritySuite() {
  const { canAction } = useAuth();
  const canPreviewDemand = canAction("workforce", "manageStaffingNorms");
  const [activities, setActivities] = useState([]);
  const [locations, setLocations] = useState([]);
  const [standards, setStandards] = useState([]);

  useEffect(() => {
    if (!canPreviewDemand) return;
    let active = true;
    Promise.all([
      loadWorkforceFlexibilityAdmin(),
      loadWorkforceLaborStandards(),
    ]).then(([admin, laborRows]) => {
      if (!active) return;
      setActivities(admin.activities || []);
      setLocations(admin.locations || []);
      setStandards(laborRows || []);
    }).catch(() => {
      if (!active) return;
      setActivities([]);
      setLocations([]);
      setStandards([]);
    });
    return () => { active = false; };
  }, [canPreviewDemand]);

  return <>
    <WorkforceActivityStudio />
    <WorkforceDemandProof activities={activities} locations={locations} standards={standards} />
  </>;
}
