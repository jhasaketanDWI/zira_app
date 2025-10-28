import React, { useState, useEffect, useRef, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import BacklogView from "../pmpages/pmbacklog/Pmbacklogview";
import {
  ItemDetailModal,
  EditSprintModal,
  StartSprintModal,
  CreateEpicModal,
  CompleteSprintModal,
} from "../pmpages/pmbacklog/PmBacklogModals";

export default function Pmbacklo() {
  const { projectId } = useParams();
  const navigate = useNavigate();

  const [boardData, setBoardData] = useState(null);
  const [users, setUsers] = useState([]);
  const [projectMembers, setProjectMembers] = useState([]);
  const [epics, setEpics] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [projectName, setProjectName] = useState("");
  const [selectedEpicId, setSelectedEpicId] = useState(null);

  const [draggedItemId, setDraggedItemId] = useState(null);
  const [activePanel, setActivePanel] = useState(null);
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const [selectedItemId, setSelectedItemId] = useState(null);
 
const selectedItem = selectedItemId ? boardData.items[selectedItemId] : null;
  const [sprintToEdit, setSprintToEdit] = useState(null);
  const [sprintToStart, setSprintToStart] = useState(null);
  const [sprintToComplete, setSprintToComplete] = useState(null);
  const [editingSprintId, setEditingSprintId] = useState(null);
  const [editingItemId, setEditingItemId] = useState(null);
  const [isEditingBacklogName, setIsEditingBacklogName] = useState(false);
  const [isCreatingSprint, setIsCreatingSprint] = useState(false);
  const [isCreatingEpic, setIsCreatingEpic] = useState(false);
  const [newSprintName, setNewSprintName] = useState("");

  const sprintNameInputRef = useRef(null);
  const backlogNameInputRef = useRef(null);
  const itemNameInputRef = useRef(null);
  const newSprintInputRef = useRef(null);

  useEffect(() => {
    const fetchInitialData = async () => {
      if (!projectId) {
        setError("Project ID is missing from the URL.");
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      const authToken = localStorage.getItem("authToken");
      if (!authToken) {
        navigate("/login");
        return;
      }

      try {
        const sprintDashboardUrl = `http://127.0.0.1:8000/api/sprints/dashboard/?project=${projectId}`;
        const projectDataUrl = `http://127.0.0.1:8000/api/projects/${projectId}/`;

        const [sprintResponse, projectResponse] = await Promise.all([
          fetch(sprintDashboardUrl, {
            headers: { Authorization: `Bearer ${authToken}` },
          }),
          fetch(projectDataUrl, {
            headers: { Authorization: `Bearer ${authToken}` },
          }),
        ]);

        if (!sprintResponse.ok || !projectResponse.ok) {
          throw new Error(`Failed to fetch all necessary data.`);
        }

        const sprintData = await sprintResponse.json();
        const projectData = await projectResponse.json();

        const allSprintsFromNewAPI = [
          ...(sprintData.active_sprints || []),
          ...(sprintData.upcoming_sprints || []),
          ...(sprintData.completed_sprints || []),
        ];
        const allTasksFromOldAPI = projectData.tasks || [];

        const formattedBoardData = {
          items: {},
          sprints: [],
          backlog: { id: "backlog", name: "Backlog", itemIds: [] },
          itemCounter: allTasksFromOldAPI.length,
        };

        allTasksFromOldAPI.forEach((task) => {
          if (task.priority && typeof task.priority === "string") {
            const priorityStr = task.priority;
            task.priority =
              priorityStr.charAt(0).toUpperCase() +
              priorityStr.slice(1).toLowerCase();
          }
          formattedBoardData.items[task.id] = {
            ...task,
            assignee:
              task.assignees.length > 0 ? task.assignees[0].user.id : null,
          };
        });

        formattedBoardData.sprints = allSprintsFromNewAPI.map((sprint) => ({
          id: sprint.id,
          name: sprint.name,
          goal: sprint.goal,
          startDate: sprint.start_date,
          endDate: sprint.end_date,
          isActive: sprint.is_active,
          is_ended: sprint.is_ended,
          epic: sprint.epic,

          itemIds: (sprint.tasks || []).map((task) => task.id),
        }));

        formattedBoardData.backlog.itemIds = allTasksFromOldAPI
          .filter((task) => task.sprint === null)
          .map((task) => task.id);

        const transformedUsers = (projectData.members || []).map((member) => ({
          id: member.user.id,
          membershipId: member.id,
          name:
            member.user.first_name && member.user.last_name
              ? `${member.user.first_name} ${member.user.last_name}`.trim()
              : member.user.email,
          email: member.user.email,
        }));

        setProjectName(projectData.name || "");
        setBoardData(formattedBoardData);
        setUsers(transformedUsers);
        setEpics(projectData.epics || []);
        setProjectMembers(projectData.members || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    };

    fetchInitialData();
  }, [projectId, navigate]);

  const handleAddNewSprint = async (e) => {
    e.preventDefault();
    if (newSprintName.trim() === "") return;

    const today = new Date();
    const twoWeeksFromNow = new Date(
      today.getTime() + 14 * 24 * 60 * 60 * 1000
    );

    const formatDateForAPI = (date) => {
      const year = date.getFullYear();
      const month = (date.getMonth() + 1).toString().padStart(2, "0");
      const day = date.getDate().toString().padStart(2, "0");
      return `${year}-${month}-${day}`;
    };

    const newSprintPayload = {
      name: newSprintName,
      goal: "",
      project: parseInt(projectId, 10),
      epic: selectedEpicId,
      start_date: formatDateForAPI(today),
      end_date: formatDateForAPI(twoWeeksFromNow),
    };

    const fullUrl = `http://127.0.0.1:8000/api/sprints/`;
    const authToken = localStorage.getItem("authToken");

    try {
      const response = await fetch(fullUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify(newSprintPayload),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(
          JSON.stringify(errorData) || "Network response was not ok."
        );
      }

      const createdSprint = await response.json();
      setBoardData((prevData) => ({
        ...prevData,
        sprints: [...prevData.sprints, { ...createdSprint, itemIds: [] }],
      }));
      setError(null);
    } catch (error) {
      setError("Failed to create the sprint. Please try again.");
    }

    setNewSprintName("");
    setIsCreatingSprint(false);
  };

  const handleUpdateSprint = async (sprintId, updates) => {
    const originalBoardData = boardData;

    setBoardData((prev) => ({
      ...prev,
      sprints: prev.sprints.map((s) =>
        s.id === sprintId
          ? {
              ...s,
              name: updates.name,
              goal: updates.goal,
              startDate: updates.start_date,
              endDate: updates.end_date,
              duration: updates.duration,
            }
          : s
      ),
    }));

    const fullUrl = `http://127.0.0.1:8000/api/sprints/${sprintId}/`;
    const authToken = localStorage.getItem("authToken");
    const payload = { ...updates };

    if (payload.duration !== undefined) {
      payload.duration = parseInt(payload.duration, 10);
      if (isNaN(payload.duration)) {
        payload.duration = 0;
      }
    }

    try {
      const response = await fetch(fullUrl, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error("Server rejected the update.");
      }

      const updatedSprintFromServer = await response.json();
      setBoardData((prev) => ({
        ...prev,
        sprints: prev.sprints.map((s) =>
          s.id === sprintId ? { ...s, ...updatedSprintFromServer } : s
        ),
      }));

      console.log(" Sprint updated successfully:", updatedSprintFromServer);
    } catch (error) {
      console.error("❌ Update sprint error, rolling back UI:", error);
      setError("Failed to update sprint. Your changes have been reverted.");
      setBoardData(originalBoardData);
    }
  };

  const handleStartSprint = async (sprintId, sprintData) => {
    const originalBoardData = boardData;

    setBoardData((prev) => {
      const newSprints = prev.sprints.map((s) => {
        if (s.isActive && s.id !== sprintId) {
          return { ...s, isActive: false };
        }
        if (s.id === sprintId) {
          return { ...s, ...sprintData, isActive: true };
        }
        return s;
      });
      return { ...prev, sprints: newSprints };
    });

    setSprintToStart(null);

    const authToken = localStorage.getItem("authToken");
    const fullUrl = `http://127.0.0.1:8000/api/sprints/${sprintId}/activate/`;
    const payload = {
      name: sprintData.name,
      goal: sprintData.goal,
      start_date: sprintData.startDate,
      end_date: sprintData.endDate,
    };

    try {
      const response = await fetch(fullUrl, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error("Server rejected the request.");
      }

      const updatedSprintFromServer = await response.json();
      setBoardData((prev) => ({
        ...prev,
        sprints: prev.sprints.map((s) =>
          s.id === sprintId ? { ...s, ...updatedSprintFromServer } : s
        ),
      }));

      console.log("✅ Sprint started and saved successfully.");
    } catch (error) {
      console.error(
        "❌ Failed to start sprint, rolling back UI change:",
        error
      );
      setError("Failed to start the sprint. Please try again.");
      setBoardData(originalBoardData);
    }
  };

  const handleDeleteSprint = async (sprintId) => {
    const fullUrl = `http://127.0.0.1:8000/api/sprints/${sprintId}/`;
    const authToken = localStorage.getItem("authToken");

    try {
      const response = await fetch(fullUrl, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!response.ok) throw new Error("Network response was not ok.");

      setBoardData((prev) => {
        const sprintToDelete = prev.sprints.find((s) => s.id === sprintId);
        const itemsToMove = sprintToDelete ? sprintToDelete.itemIds : [];
        return {
          ...prev,
          sprints: prev.sprints.filter((s) => s.id !== sprintId),
          backlog: {
            ...prev.backlog,
            itemIds: [...prev.backlog.itemIds, ...itemsToMove],
          },
        };
      });
    } catch (error) {
      console.error("Error deleting sprint:", error);
    }
  };

  const createTaskOnBackend = async (taskPayload) => {
    const authToken = localStorage.getItem("authToken");
    const fullUrl = `http://127.0.0.1:8000/api/tasks/`;

    try {
      const response = await fetch(fullUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify(taskPayload),
      });

      const createdTask = await response.json();
      if (!response.ok) {
        console.error("Backend error response:", createdTask);
        throw new Error(JSON.stringify(createdTask));
      }

      console.log("✅ SUCCESS: Task created on backend:", createdTask);
      return createdTask;
    } catch (error) {
      console.error(
        "❌ FAILURE: Could not create task on backend.",
        "Error:",
        error.message
      );
      setError("Failed to create the task. Please check the console.");
      return null;
    }
  };

  // In BacklogPage.jsx

  const handleCreateSubtask = async (parentItemId, subtaskTitle) => {
  const authToken = localStorage.getItem("authToken");
  const currentUserMembership = projectMembers.find(
    (member) =>
      member.user.id === parseInt(localStorage.getItem("userId"), 10)
  );

  if (!currentUserMembership) {
    setError("Cannot create subtask: User is not a project member.");
    return;
  }

  const subtaskPayload = {
    title: subtaskTitle,
    project: parseInt(projectId, 10),
    status_id: 1,
    priority: "MEDIUM",
    task_type: "FEATURE",
    reporter: currentUserMembership.id,
  };

  const newSubtask = await createTaskOnBackend(subtaskPayload);

  if (newSubtask) {
    try {
      const linkPayload = { parent_task: parentItemId };
      const linkUrl = `http://127.0.0.1:8000/api/tasks/${newSubtask.id}/parent/`;

      const linkResponse = await fetch(linkUrl, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify(linkPayload),
      });

      if (!linkResponse.ok)
        throw new Error("Failed to link subtask to parent.");

      console.log("✅ SUCCESS: Subtask linked to parent.");

      // --- UI STATE UPDATES ---
      setBoardData((prevData) => {
        const parentItem = prevData.items[parentItemId];
        const updatedSubtasks = [...(parentItem.subtasks || []), newSubtask];

        const location = findItemLocation(parentItemId);
        const listId = location ? location.listId : null;
        
        let newSprints = [...prevData.sprints];
        let newBacklog = { ...prevData.backlog };

        if (listId) {
          if (listId === "backlog") {
            const parentIndex = newBacklog.itemIds.indexOf(parentItemId);
            const newItemIds = [...newBacklog.itemIds];
            newItemIds.splice(parentIndex + 1, 0, newSubtask.id);
            newBacklog.itemIds = newItemIds;
          } else {
            newSprints = prevData.sprints.map((sprint) => {
              if (sprint.id === listId) {
                const parentIndex = sprint.itemIds.indexOf(parentItemId);
                const newItemIds = [...sprint.itemIds];
                newItemIds.splice(parentIndex + 1, 0, newSubtask.id);
                return { ...sprint, itemIds: newItemIds };
              }
              return sprint;
            });
          }
        }

        return {
          ...prevData,
          items: {
            ...prevData.items,
            [newSubtask.id]: { ...newSubtask, parent: parentItemId },
            [parentItemId]: { ...parentItem, subtasks: updatedSubtasks },
          },
          sprints: newSprints,
          backlog: newBacklog,
        };
      });

      if (selectedItem && selectedItem.id === parentItemId) {
        setSelectedItem((prev) => {
          const updatedSubtasks = [...(prev.subtasks || []), newSubtask];
          return { ...prev, subtasks: updatedSubtasks };
        });
      }
    } catch (error) {
      console.error("❌ FAILURE: Could not link subtask.", error);
    }
  }
};
  const handleUpdateItemDB = async (itemId, updates) => {
    const authToken = localStorage.getItem("authToken");

    const projectIdInt = parseInt(projectId, 10);

    const updateKey = Object.keys(updates)[0];
    if (!updateKey) {
      console.error("Update function called with empty updates object.");
      return;
    }

    let fullUrl = `http://127.0.0.1:8000/api/tasks/${itemId}/`;
    let payload = {};

    switch (updateKey) {
      case "status_id":
        fullUrl += "status/";
        payload = {
          status: updates.status_id,
          project: projectIdInt,
        };
        break;

      case "assignee":
        fullUrl += "assignees/";

        const assigneeId = updates.assignee;
        payload = {
          assignees: assigneeId ? [assigneeId] : [],
          project: projectIdInt,
        };
        break;

      case "due_date":
        fullUrl += "due-date/";
        payload = {
          due_date: updates.due_date,
          project: projectIdInt,
        };
        break;

      case "story_points":
        fullUrl += "story-points/";
        const points = parseInt(updates.story_points, 10);
        payload = {
          story_points: isNaN(points) ? null : points,
        };
        break;

      case "description":
        fullUrl += "description/";
        payload = {
          description: updates.description,
        };
        break;

      case "sprint":
        fullUrl += "sprint/";
        payload = {
          sprint: updates.sprint,
        };
        break;

      case "priority":
        fullUrl += "priority/";
        payload = { ...updates };
        if (payload.priority) {
          payload.priority = payload.priority.toUpperCase();
        }
        break;

      case "title":
       payload = {
          title: updates.title,
        };
        break;

      default:
        console.error(
          `❌ Unhandled update key: '${updateKey}'. No API endpoint is configured for this field.`
        );
        return;
    }

    console.log(
      `Attempting PATCH: ${fullUrl}`,
      `Payload: ${JSON.stringify(payload)}`
    );

    try {
      const response = await fetch(fullUrl, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify(payload),
      });

      const responseData = await response.json();

      if (!response.ok) {
        throw new Error(
          JSON.stringify(responseData) ||
            `Request failed with status ${response.status}`
        );
      }

      console.log(
        `✅ SUCCESS: Item ${itemId} updated.`,
        "Response:",
        responseData
      );
      return responseData;
    } catch (error) {
      console.error(
        `❌ FAILURE: Could not update item ${itemId}.`,
        "Error:",
        error.message
      );
      return null;
    }
  };

  const handleCreateItem = async (listId) => {
    const currentUserId = parseInt(localStorage.getItem("userId"), 10);
    if (!currentUserId) {
      setError("Could not find user ID. Please log in again.");
      return;
    }

    const currentUserMembership = projectMembers.find(
      (member) => member.user.id === currentUserId
    );
    if (!currentUserMembership) {
      setError(
        "Your user is not a member of this project. Cannot create task."
      );
      return;
    }

    const reporterMembershipId = currentUserMembership.id;

    const payload = {
      title: "New Task",
      description: "",
      project: parseInt(projectId, 10),
      sprint: listId === "backlog" ? null : listId,
      epic: epics.length > 0 ? epics[0].id : null,
      status_id: 1,
      priority: "MEDIUM",
      task_type: "FEATURE",
      assignees: [],
      reporter: reporterMembershipId,
      tags: [],
    };

    const fullUrl = `http://127.0.0.1:8000/api/tasks/`;
    const authToken = localStorage.getItem("authToken");

    try {
      const response = await fetch(fullUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(
          JSON.stringify(errorData) || "Network response was not ok."
        );
      }

      const createdItem = await response.json();

      setBoardData((prev) => {
        const newItems = { ...prev.items, [createdItem.id]: createdItem };

        const sprints = prev.sprints.map((s) =>
          s.id === listId
            ? { ...s, itemIds: [...s.itemIds, createdItem.id] }
            : s
        );
        const backlog =
          listId === "backlog"
            ? {
                ...prev.backlog,
                itemIds: [...prev.backlog.itemIds, createdItem.id],
              }
            : prev.backlog;

        return {
          ...prev,
          items: newItems,
          sprints,
          backlog,
          itemCounter: prev.itemCounter + 1,
        };
      });
    } catch (error) {
      setError(
        "Failed to create task. Check console for details from the server."
      );
    }
  };

  const handleDeleteItem = async (itemId) => {
    const fullUrl = `http://127.0.0.1:8000/api/tasks/${itemId}/`;
    const authToken = localStorage.getItem("authToken");

    try {
      const response = await fetch(fullUrl, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!response.ok) throw new Error("Network response was not ok.");

      setBoardData((prev) => {
        const newItems = { ...prev.items };
        delete newItems[itemId];

        const sprints = prev.sprints.map((s) => ({
          ...s,
          itemIds: s.itemIds.filter((id) => id !== itemId),
        }));
        const backlog = {
          ...prev.backlog,
          itemIds: prev.backlog.itemIds.filter((id) => id !== itemId),
        };

        return { ...prev, items: newItems, sprints, backlog };
      });
    } catch (error) {
      console.error("Error deleting item:", error);
    }
  };

  const handleAddNewEpic = async (formData) => {
    const payload = {
      title: formData.title,
      description: formData.description,
      project: parseInt(projectId, 10),
    };

    const fullUrl = `http://127.0.0.1:8000/api/epics/`;
    const authToken = localStorage.getItem("authToken");

    try {
      const response = await fetch(fullUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(JSON.stringify(errorData));
      }
      const createdEpic = await response.json();
      setEpics((prev) => [...prev, createdEpic]);
      setIsCreatingEpic(false);
    } catch (error) {
      setError("Failed to create epic. Please try again.");
    }
  };

  const handleOpenCompleteSprintModal = (sprintId) => {
    const sprint = boardData.sprints.find((s) => s.id === sprintId);
    if (!sprint || !sprint.isActive) return;

    const completedIssues = sprint.itemIds.filter(
      (id) => boardData.items[id].status.title.toUpperCase() === "DONE"
    );
    const openIssues = sprint.itemIds.filter(
      (id) => boardData.items[id].status.title.toUpperCase() !== "DONE"
    );

    const futureSprints = boardData.sprints.filter(
      (s) => !s.isActive && s.id !== sprintId
    );

    setSprintToComplete({
      ...sprint,
      completedCount: completedIssues.length,
      openCount: openIssues.length,
      openIssueIds: openIssues,
      futureSprints: futureSprints,
    });
  };

  const handleCompleteSprint = async (sprintId, openIssueIds, destination) => {
    const authToken = localStorage.getItem("authToken");

    try {
      const newSprintId =
        destination === "backlog" ? null : parseInt(destination, 10);

      const moveTasksPromises = openIssueIds.map((taskId) => {
        const moveUrl = `http://127.0.0.1:8000/api/tasks/${taskId}/sprint/`;
        return fetch(moveUrl, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${authToken}`,
          },
          body: JSON.stringify({ sprint: newSprintId }),
        });
      });
      await Promise.all(moveTasksPromises);
      const completeSprintUrl = `http://127.0.0.1:8000/api/sprints/${sprintId}/end/`;
      const completeSprintResponse = await fetch(completeSprintUrl, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },

        body: JSON.stringify({ is_ended: true }),
      });

      if (!completeSprintResponse.ok) {
        throw new Error("Tasks were moved, but failed to complete the sprint.");
      }

      setBoardData((prevData) => {
        const newSprints = prevData.sprints.map((sprint) => {
          if (sprint.id === sprintId) {
            return {
              ...sprint,
              isActive: false,
              is_ended: true,
              itemIds: sprint.itemIds.filter(
                (id) => !openIssueIds.includes(id)
              ),
            };
          }
          if (sprint.id === newSprintId) {
            return {
              ...sprint,
              itemIds: [...sprint.itemIds, ...openIssueIds],
            };
          }
          return sprint;
        });

        const newBacklog =
          destination === "backlog"
            ? {
                ...prevData.backlog,
                itemIds: [...prevData.backlog.itemIds, ...openIssueIds],
              }
            : prevData.backlog;

        return {
          ...prevData,
          sprints: newSprints,
          backlog: newBacklog,
        };
      });
    } catch (error) {
      console.error("Error completing sprint:", error);
      setError("Failed to complete the sprint. Please check the console.");
    } finally {
      setSprintToComplete(null);
    }
  };

 const handleFetchComments = async (taskId) => {
  const authToken = localStorage.getItem("authToken");
  try {
    const response = await fetch(
      `http://127.0.0.1:8000/api/tasks/${taskId}/activities/`,
      {
        headers: { Authorization: `Bearer ${authToken}` },
      }
    );
    if (!response.ok) throw new Error("Failed to fetch comments.");
    const activities = await response.json();

    setBoardData((prev) => ({
      ...prev,
      items: {
        ...prev.items,
        [taskId]: { ...prev.items[taskId], activity_log: activities },
      },
    }));
  } catch (error) {
    console.error("Error fetching comments:", error);
  }
};

const handleAddComment = async (taskId, commentBody) => {
  if (!commentBody.trim()) return;
  const authToken = localStorage.getItem("authToken");
  try {
    const response = await fetch(
      `http://127.0.0.1:8000/api/tasks/${taskId}/add-activity/`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ comment_body: commentBody }),
      }
    );
    if (!response.ok) throw new Error("Failed to post comment.");
    const newActivity = await response.json();

    setBoardData((prev) => {
      const task = prev.items[taskId];
      return {
        ...prev,
        items: {
          ...prev.items,
          [taskId]: {
            ...task,
            activity_log: [...(task.activity_log || []), newActivity],
          },
        },
      };
    });
  } catch (error) {
    console.error("Error adding comment:", error);
    setError("Could not post your comment.");
  }
};

const handleUpdateComment = async (taskId, activityId, commentBody) => {
  const authToken = localStorage.getItem("authToken");
  try {
    const response = await fetch(
      `http://127.0.0.1:8000/api/tasks/${taskId}/update-activity/${activityId}/`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ comment_body: commentBody }),
      }
    );
    if (!response.ok) throw new Error("Failed to update comment.");
    const updatedActivity = await response.json();

    const updateLog = (log) =>
      log.map((act) => (act.id === activityId ? updatedActivity : act));
      
    setBoardData((prev) => ({
      ...prev,
      items: {
        ...prev.items,
        [taskId]: {
          ...prev.items[taskId],
          activity_log: updateLog(prev.items[taskId].activity_log),
        },
      },
    }));
  } catch (error) {
    console.error("Error updating comment:", error);
    setError("Could not update your comment.");
  }
};

const handleDeleteComment = async (taskId, activityId) => {
  const authToken = localStorage.getItem("authToken");
  try {
    const response = await fetch(
      `http://127.0.0.1:8000/api/tasks/${taskId}/delete-activity/${activityId}/`,
      {
        method: "DELETE",
        headers: { Authorization: `Bearer ${authToken}` },
      }
    );
    if (!response.ok) throw new Error("Failed to delete comment.");

    const filterLog = (log) => log.filter((act) => act.id !== activityId);

    setBoardData((prev) => ({
      ...prev,
      items: {
        ...prev.items,
        [taskId]: {
          ...prev.items[taskId],
          activity_log: filterLog(prev.items[taskId].activity_log || []),
        },
      },
    }));
  } catch (error) {
    console.error("Error deleting comment:", error);
    setError("Could not delete your comment.");
  }
};

  useEffect(() => {
    if (isCreatingSprint) newSprintInputRef.current?.focus();
    if (editingSprintId) sprintNameInputRef.current?.focus();
    if (isEditingBacklogName) backlogNameInputRef.current?.focus();
    if (editingItemId) itemNameInputRef.current?.focus();
  }, [isCreatingSprint, editingSprintId, isEditingBacklogName, editingItemId]);
  

 const handleItemClick = (item) => setSelectedItemId(item.id);
const handleCloseModal = () => setSelectedItemId(null);
  const handleCloseEditSprintModal = () => setSprintToEdit(null);
  const handleCloseStartSprintModal = () => setSprintToStart(null);
  const handleCloseCreateEpicModal = () => setIsCreatingEpic(false);
  const handleCloseCompleteSprintModal = () => setSprintToComplete(null);

  const handleUpdateItem = async (itemId, updates) => {
    const updatedItemFromServer = await handleUpdateItemDB(itemId, updates);

    if (!updatedItemFromServer) {
      return;
    }

    const finalUpdates = {
      ...updates,
      ...updatedItemFromServer,
    };

    if (finalUpdates.assignees) {
      finalUpdates.assignee =
        finalUpdates.assignees.length > 0
          ? finalUpdates.assignees[0].user.id
          : null;
    }

    if (finalUpdates.priority && typeof finalUpdates.priority === "string") {
      const priorityStr = finalUpdates.priority;
      finalUpdates.priority =
        priorityStr.charAt(0).toUpperCase() +
        priorityStr.slice(1).toLowerCase();
    }

    setBoardData((prevData) => {
      const newItems = {
        ...prevData.items,
        [itemId]: {
          ...prevData.items[itemId],
          ...finalUpdates,
        },
      };
      return { ...prevData, items: newItems };
    });

    
  };

  const handleStartRenameSprint = (sprintId) => setEditingSprintId(sprintId);
  const handleStartRenameBacklog = () => setIsEditingBacklogName(true);
  const handleStartRenameItem = (itemId) => setEditingItemId(itemId);

  const handleRenameSprint = (sprintId, newName) => {
    handleUpdateSprint(sprintId, { name: newName || "Untitled Sprint" });
    setEditingSprintId(null);
  };

  const handleRenameItem = (itemId, newTitle) => {
    handleUpdateItem(itemId, { title: newTitle || "Untitled Item" });
    setEditingItemId(null);
  };

  const handleRenameBacklog = (newName) => {
    setBoardData((prev) => ({
      ...prev,
      backlog: { ...prev.backlog, name: newName || "Backlog" },
    }));
    setIsEditingBacklogName(false);
  };

  const handleDragStart = (e, itemId) => {
    setDraggedItemId(itemId);
    e.dataTransfer.effectAllowed = "move";
    setTimeout(() => {
      e.target.style.opacity = "0.5";
    }, 0);
  };

  const handleDragEnd = (e) => {
    if (e.target) e.target.style.opacity = "1";
    setDraggedItemId(null);
  };

  const handleDragOver = (e) => e.preventDefault();

  const findItemLocation = (itemId) => {
    if (!boardData) return null;
    for (const sprint of boardData.sprints) {
      if (sprint.itemIds.includes(itemId))
        return { listId: sprint.id, sprintName: sprint.name };
    }
    if (boardData.backlog.itemIds.includes(itemId))
      return { listId: "backlog", sprintName: boardData.backlog.name };
    return null;
  };

  const handleDrop = (e, targetListId) => {
    e.preventDefault();
    if (!draggedItemId) return;

    const sourceLocation = findItemLocation(draggedItemId);
    if (!sourceLocation) return;

    const { listId: sourceListId } = sourceLocation;
    if (sourceListId === targetListId && !e.target.closest("[data-item-id]"))
      return;

    const sprintId = targetListId === "backlog" ? null : targetListId;
    handleUpdateItemDB(draggedItemId, { sprint: sprintId });

    const newBoardData = JSON.parse(JSON.stringify(boardData));
    let sourceList =
      sourceListId === "backlog"
        ? newBoardData.backlog.itemIds
        : newBoardData.sprints.find((s) => s.id === sourceListId).itemIds;
    const sourceIndex = sourceList.indexOf(draggedItemId);
    if (sourceIndex > -1) sourceList.splice(sourceIndex, 1);

    let targetList =
      targetListId === "backlog"
        ? newBoardData.backlog.itemIds
        : newBoardData.sprints.find((s) => s.id === targetListId).itemIds;
    const dropTargetElement = e.target.closest("[data-item-id]");
    let dropIndex = targetList.length;

    if (dropTargetElement) {
      const dropTargetId = dropTargetElement.getAttribute("data-item-id");
      const index = targetList.indexOf(dropTargetId);
      if (index !== -1) dropIndex = index;
    }

    targetList.splice(dropIndex, 0, draggedItemId);
    setBoardData(newBoardData);
  };

  const handlePanelToggle = (panelName) =>
    setActivePanel((current) => (current === panelName ? null : panelName));
  const handleMoreMenuToggle = () => setIsMoreMenuOpen((prev) => !prev);

  const filteredItems = useMemo(() => {
    if (!boardData || !boardData.items) return {};
    if (!searchTerm) return boardData.items;

    const lowercasedFilter = searchTerm.toLowerCase();
    const filtered = {};
    for (const itemId in boardData.items) {
      const item = boardData.items[itemId];
      if (
        item.title.toLowerCase().includes(lowercasedFilter) ||
        item.id.toString().toLowerCase().includes(lowercasedFilter)
      ) {
        filtered[itemId] = item;
      }
    }
    return filtered;
  }, [searchTerm, boardData]);

  const backlogItems = useMemo(() => {
    if (!boardData || !boardData.backlog) return [];
    return boardData.backlog.itemIds
      .map((id) => filteredItems[id])
      .filter(Boolean);
  }, [boardData, filteredItems]);

  const usersWithUnassigned = useMemo(
    () => [{ id: null, name: "Unassigned" }, ...users],
    [users]
  );

  
  const epicOptions = useMemo(() => {
    if (!epics) return [];
    const options = epics.map((epic) => ({
      value: epic.id,
      label: epic.title,
    }));
    options.push({ value: "create", label: "+ Create Epic" });
    return options;
  }, [epics]);

  const { uncompletedSprints, completedSprints } = useMemo(() => {
    if (!boardData || !boardData.sprints) {
      return { uncompletedSprints: [], completedSprints: [] };
    }

    const sprintsToDisplay =
      selectedEpicId === null
        ? boardData.sprints
        : boardData.sprints.filter((sprint) => sprint.epic === selectedEpicId);

    const uncompleted = [];
    const completed = [];
    sprintsToDisplay.forEach((sprint) => {
      if (sprint.is_ended) {
        completed.push(sprint);
      } else {
        uncompleted.push(sprint);
      }
    });

    return { uncompletedSprints: uncompleted, completedSprints: completed };
  }, [selectedEpicId, boardData]);

  if (isLoading) {
  return (
    <div
      className="flex flex-col items-center justify-center h-screen"
      style={{ background: 'linear-gradient(135deg, #FFCDB2 0%, #FFB4A2 30%, #E5989B 70%, #B5828C 100%)' }}
    >
      {/* Spinner Element */}
      <div className="w-12 h-12 border-4 border-white border-solid rounded-full border-t-transparent animate-spin"></div>
      
      {/* Optional Loading Text */}
      <p className="mt-4 text-lg font-semibold text-white">Loading Backlog...</p>
    </div>
  );
}

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-red-600">
        Error: {error}
      </div>
    );
  }

  const currentUserId = parseInt(localStorage.getItem("userId"), 10);

  return (
    <>
      <BacklogView
        boardData={boardData}
        users={users}
        usersWithUnassigned={usersWithUnassigned}
        epicOptions={epicOptions}
        filteredItems={filteredItems}
        backlogItems={backlogItems}
        searchTerm={searchTerm}
        uncompletedSprints={uncompletedSprints}
        completedSprints={completedSprints}
        setSearchTerm={setSearchTerm}
        activePanel={activePanel}
        isMoreMenuOpen={isMoreMenuOpen}
        editingSprintId={editingSprintId}
        editingItemId={editingItemId}
        isEditingBacklogName={isEditingBacklogName}
        isCreatingSprint={isCreatingSprint}
        newSprintName={newSprintName}
        sprintNameInputRef={sprintNameInputRef}
        backlogNameInputRef={backlogNameInputRef}
        itemNameInputRef={itemNameInputRef}
        newSprintInputRef={newSprintInputRef}
        setIsCreatingEpic={setIsCreatingEpic}
        handlePanelToggle={handlePanelToggle}
        handleMoreMenuToggle={handleMoreMenuToggle}
        setSprintToEdit={setSprintToEdit}
        handleDeleteSprint={handleDeleteSprint}
        setSprintToStart={setSprintToStart}
        handleOpenCompleteSprintModal={handleOpenCompleteSprintModal}
        handleDragOver={handleDragOver}
        handleDrop={handleDrop}
        handleDragStart={handleDragStart}
        handleDragEnd={handleDragEnd}
        handleItemClick={handleItemClick}
        handleUpdateItem={handleUpdateItem}
        handleStartRenameSprint={handleStartRenameSprint}
        handleStartRenameItem={handleStartRenameItem}
        handleRenameSprint={handleRenameSprint}
        handleRenameItem={handleRenameItem}
        handleDeleteItem={handleDeleteItem}
        handleCreateItem={handleCreateItem}
        handleStartRenameBacklog={handleStartRenameBacklog}
        handleRenameBacklog={handleRenameBacklog}
        setIsCreatingSprint={setIsCreatingSprint}
        setNewSprintName={setNewSprintName}
        handleAddNewSprint={handleAddNewSprint}
        selectedEpicId={selectedEpicId}
        setSelectedEpicId={setSelectedEpicId}
        epics={epics}
      />

      <ItemDetailModal
        item={selectedItem}
        users={usersWithUnassigned}
        sprintName={
          selectedItem && boardData
            ? findItemLocation(selectedItem.id)?.sprintName
            : ""
        }
        onClose={handleCloseModal}
        onUpdate={handleUpdateItem}
        onCreateSubtask={handleCreateSubtask}
        onFetchComments={handleFetchComments}
        onAddComment={handleAddComment}
        onUpdateComment={handleUpdateComment}
        onDeleteComment={handleDeleteComment}
         currentUserId={currentUserId}
      />
      <EditSprintModal
        sprint={sprintToEdit}
        epics={epics}
        onClose={handleCloseEditSprintModal}
        onUpdate={handleUpdateSprint}
      />
      <StartSprintModal
        sprint={sprintToStart}
        onClose={handleCloseStartSprintModal}
        onStart={handleStartSprint}
      />
      {isCreatingEpic && (
        <CreateEpicModal
          onClose={handleCloseCreateEpicModal}
          onCreate={handleAddNewEpic}
          projectName={projectName}
          currentUser={users.find((u) => u.id === currentUserId)}
        />
      )}
      {sprintToComplete && (
        <CompleteSprintModal
          sprint={sprintToComplete}
          onClose={handleCloseCompleteSprintModal}
          onComplete={handleCompleteSprint}
        />
      )}
    </>
  );
}

