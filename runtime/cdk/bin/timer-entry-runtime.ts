#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { TimerEntryRuntimeStack } from "../lib/timer-entry-runtime-stack";

const app = new cdk.App();
new TimerEntryRuntimeStack(app, "TimerEntryRuntimeStack");

