/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
package org.apache.ambari.server.agent;

import com.fasterxml.jackson.annotation.JsonProperty;

public class CommandReport {

  private String role;
  private String actionId;
  private String stdout;
  private String stderr;
  private String structuredOut;
  private String status;
  int exitCode;
  private String serviceName;
  private long taskId;
  private String clusterId;
  private String roleCommand;
  private String customCommand;

  @JsonProperty("customCommand")
  public String getCustomCommand() {
    return customCommand;
  }

  @JsonProperty("customCommand")
  public void setCustomCommand(String customCommand) {
    this.customCommand = customCommand;
  }

  @JsonProperty("taskId")
  public long getTaskId() {
    return taskId;
  }
  
  @JsonProperty("taskId")
  public void setTaskId(long taskId) {
    this.taskId = taskId;
  }

  @JsonProperty("actionId")
  public String getActionId() {
    return this.actionId;
  }
  
  @JsonProperty("actionId")
  public void setActionId(String actionId) {
    this.actionId = actionId;
  }
  
  @JsonProperty("stderr")
  public String getStdErr() {
    return this.stderr;
  }
  
  @JsonProperty("stderr")
  public void setStdErr(String stderr) {
    this.stderr = stderr;
  }
  
  @JsonProperty("exitcode")
  public int getExitCode() {
    return this.exitCode;
  }
  
  @JsonProperty("exitcode")
  public void setExitCode(int exitCode) {
    this.exitCode = exitCode;
  }
  
  @JsonProperty("stdout")
  public String getStdOut() {
    return this.stdout;
  }
  
  @JsonProperty("stdout")
  public void setStdOut(String stdout) {
    this.stdout = stdout;
  }

  @JsonProperty("structuredOut")
  public String getStructuredOut() {
    return this.structuredOut;
  }


  @JsonProperty("structuredOut")
  public void setStructuredOut(String structuredOut) {
    this.structuredOut = structuredOut;
  }

  @JsonProperty("roleCommand")
  public String getRoleCommand() {
    return this.roleCommand;
  }

  @JsonProperty("roleCommand")
  public void setRoleCommand(String roleCommand) {
    this.roleCommand = roleCommand;
  }

  @JsonProperty("role")
  public String getRole() {
    return role;
  }
  
  @JsonProperty("role")
  public void setRole(String role) {
    this.role = role;
  }
  
  @JsonProperty("status")
  public String getStatus() {
    return status;
  }
  
  @JsonProperty("status")
  public void setStatus(String status) {
    this.status = status;
  }
  
  @JsonProperty("serviceName")
  public String getServiceName() {
    return serviceName;
  }
  
  @JsonProperty("serviceName")
  public void setServiceName(String serviceName) {
    this.serviceName = serviceName;
  }

  @JsonProperty("clusterId")
  public String getClusterId() {
    return clusterId;
  }

  @JsonProperty("clusterId")
  public void setClusterId(String clusterId) {
    this.clusterId = clusterId;
  }

  @Override
  public String toString() {
    return "CommandReport{" +
            "role='" + role + '\'' +
            ", actionId='" + actionId + '\'' +
            ", status='" + status + '\'' +
            ", exitCode=" + exitCode +
            ", clusterId='" + clusterId + '\'' +
            ", serviceName='" + serviceName + '\'' +
            ", taskId=" + taskId +
            ", roleCommand=" + roleCommand +
            ", customCommand=" + customCommand +
            '}';
  }
}
