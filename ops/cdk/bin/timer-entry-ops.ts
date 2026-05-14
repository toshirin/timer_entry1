#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { TimerEntryOpsStack } from "../lib/timer-entry-ops-stack";

const app = new cdk.App();
new TimerEntryOpsStack(app, "TimerEntryOpsStack");
