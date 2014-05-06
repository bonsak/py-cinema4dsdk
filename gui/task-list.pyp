# Copyright (c) 2014  Donovan Keith
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
r"""
    py-cinema4dsdk/gui/task-list.pyp
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    description:
        This Tasklist plugin demonstrates common issues when
        working with dialogs in Cinema 4D:

        1. Creating and updating a dynamic dialog.
        2. Saving the dialog's data within the active document.
        3. Refreshing the dialog when a new document is opened.
        4. Emulating a keyboard event, more specifically CTRL+A
        to select all the contents of a text field when a task is
        created.
    tags:
        command gui persistent-data persistent-data-undo async-dialog
        bitmap-button event-emulation
    level: medium
    links:
        http://www.plugincafe.com/forum/forum_posts.asp?TID=9828
"""

import c4d

# Unique plugin ID, get yours from http://plugincafe.com/forum/developer.asp
PLUGIN_ID = 1032046

# This structure will contain all of our resource symbols that we
# use in the TaskListDialog. Prevents pollution of the global scope.
# We can use type() to create a new type from a dictionary which will
# allow us to use attribute-access instead of bracket syntax.
res = type('res', (), dict(
    # ID of the text that displays the active document's name.
    TEXT_DOCINFO = 1001,

    # ID of the button to add a new task.
    BUTTON_NEWTASK = 3000,

    # This is the ID for the group that contains the task widgets.
    GROUP_TASKS = 2000,

    # The following IDs are required for computing the IDs for
    # each widget that is required to display the task list.
    # We also want to be compatible in case we need future
    # changes so we reserve 10 widgets that are being used
    # for each row why we currently only use two.
    # The same IDs will be used to persistently store the tasks
    # in a c4d.BaseContainer.
    DYNAMIC_TASKS_START = 100000,
    TASKWIDGET_COUNT = 10,        # Number of widgets per row (incl. buffer)
    TASKWIDGET_REALCOUNT = 3,     # The real number of widgets
    TASKWIDGET_OFFSET_STATE = 0,  # Checkbox
    TASKWIDGET_OFFSET_NAME = 1,   # Text Edit field
    TASKWIDGET_OFFSET_REMOVE = 2, # Bitmap Button

))

def IsSameNode(node_a, node_b):
    r""" Returns True if *node_a* and *node_b* are references to the
    same :class:`c4d.BaseList2D` node, False if not. Note that this
    method returns always False if any of the nodes is not alive
    anymore. """

    if not node_a or not node_b:
        return False
    if not node_a.IsAlive() or not node_b.IsAlive():
        return False
    return node_a == node_b

def GetBaseSettingsHook(doc):
    r""" Returns the SceneHook of the document that is always
    available. Displays a warning in the unlikely event that
    it is not available. """

    hook = doc.FindSceneHook(c4d.ID_BS_HOOK)
    if not hook:
        import warning
        raise warning.warn(
                '[TaskList]: BaseSettings Hook not found',
                RuntimeWarning)

    return hook

class TaskListDialog(c4d.gui.GeDialog):
    r""" This class implements creating the layout for the Task list
    and managing the user input as well as saving and loaded the
    persistent data. """

    DEFAULT_TASK_NAME = "Task"

    def __init__(self):
        super(TaskListDialog, self).__init__()

        # Keep track of the document that we used the last time we
        # updated the layout and values in the dialog.
        self._last_doc = None

        # A list of the task entries. We will load the tasks from
        # the document when required so we can safely set this
        # to None (this will also help us to find out when we
        # forgot to load the tasks).
        # Each task is a dictionary with two entries:
        #   - done (bool)
        #   - name (str)
        self._task_list = None

    def ComputeTaskId(self, task_index, offset=0):
        r""" Returns the ID of a task widget with the specified
        *task_index*. If *offset* is 0, the base ID (of the
        first widget) is returned. """

        base_id = res.DYNAMIC_TASKS_START + res.TASKWIDGET_COUNT * task_index
        return base_id + offset

    def Refresh(self, flush=True, force=False, initial=False, reload_=False):
        r""" We call this method to create the widgets for each
        task and set their state. When *flush* is True, the group
        that contains the tasks will be flushed before the widgets
        are created (this is default).

        It will also update the widget that displays the name of
        the current document.

        When *force* is True, the layout is garuanteed to be rebuilt.
        This method will otherwise check if a rebuild is actually
        necessary.

        When *reload_* is True, the tasks are being reload from the
        current document. Note that ``reload`` is a built-in name.

        *initial* should be set to True when this is the initial
        call to :meth:`Refresh` from :meth:`CreateLayout`. """

        if initial:
            flush = False
            reload_ = True
            self._last_doc = None

        # Obtain the current document and compare it with the
        # document that we have kept a reference to. If they
        # match, we don't necessarily need to rebuild the layout.
        current_doc = c4d.documents.GetActiveDocument()
        if not IsSameNode(current_doc, self._last_doc):
            self._last_doc = current_doc
            force = True
            reload_ = True

        # Update the document name in the title. Although we might
        # not actually need to rebuild the UI, the name of the
        # document could've changed.
        title_text = 'Todo In: %s' % self._last_doc.GetDocumentName()
        self.SetString(res.TEXT_DOCINFO, title_text)

        # Stop the method if we don't need to rebuild.
        if not force:
            return

        if flush:
            self.LayoutFlushGroup(res.GROUP_TASKS)
        if reload_:
            self.LoadTasks()

        # Create the option container for the BitmapButtonCustomGui.
        # We can re-use this for each bitmap button that we create.
        bmpbutton = c4d.BaseContainer()
        bmpbutton.SetBool(c4d.BITMAPBUTTON_BUTTON, True)
        bmpbutton.SetString(c4d.BITMAPBUTTON_TOOLTIP, "Remove this Task")
        bmpbutton.SetLong(c4d.BITMAPBUTTON_ICONID1, c4d.RESOURCEIMAGE_CLEARSELECTION)

        # Build the widgets for each task.
        for i, task in enumerate(self._task_list):
            base_id = self.ComputeTaskId(i)

            self.AddCheckbox(base_id + res.TASKWIDGET_OFFSET_STATE, 0, 0, 0, "")
            self.AddEditText(base_id + res.TASKWIDGET_OFFSET_NAME, c4d.BFH_SCALEFIT)
            self.AddCustomGui(base_id + res.TASKWIDGET_OFFSET_REMOVE,
                    c4d.CUSTOMGUI_BITMAPBUTTON, name="", flags=0, minw=0,
                    minh=0, customdata=bmpbutton)

            self.SetBool(base_id + res.TASKWIDGET_OFFSET_STATE, task['done'])
            self.SetString(base_id + res.TASKWIDGET_OFFSET_NAME, task['name'])
            self.Enable(base_id + res.TASKWIDGET_OFFSET_NAME, not task['done'])

        if flush:
            self.LayoutChanged(res.GROUP_TASKS)

    def SaveTasks(self):
        r""" Saves the tasks in the :attr:`_task_list` to the last
        document that we had hold of. They will be stored in a sub
        container of a SceneHook in the document that is always
        available. We use this SceneHook because it allows us to
        add undos, which is not possible for the document itself. """

        # Create the container and will it with the tasks.
        bc = c4d.BaseContainer()
        bc.SetLong(0, len(self._task_list))
        for i, task in enumerate(self._task_list):
            base_id = self.ComputeTaskId(i)
            bc.SetBool(base_id + res.TASKWIDGET_OFFSET_STATE, task['done'])
            bc.SetString(base_id + res.TASKWIDGET_OFFSET_NAME, task['name'])

        # Save to the document.
        doc = self._last_doc
        hook = GetBaseSettingsHook(doc)
        if hook:

            # No matter what happens, the undo step must be
            # closed after it was started.
            doc.StartUndo()
            try:
                doc.AddUndo(c4d.UNDOTYPE_CHANGE_SMALL, hook)
                hook.GetDataInstance().SetContainer(PLUGIN_ID, bc)
            finally:
                doc.EndUndo()

    def LoadTasks(self):
        r""" Loads tasks from the current document and puts them
        into the :attr:`_task_list` list. """

        hook = GetBaseSettingsHook(self._last_doc)
        if not hook:
            self._task_list = []
            return

        # Get the sub container and the number of tasks that
        # have been stored in it.
        bc = hook.GetDataInstance().GetContainer(PLUGIN_ID)
        task_count = max([bc.GetLong(0), 0])

        tasks = []
        for i in xrange(task_count):
            base_id = self.ComputeTaskId(i)
            task = {
                    'done': bc.GetBool(base_id + res.TASKWIDGET_OFFSET_STATE),
                    'name': bc.GetString(base_id + res.TASKWIDGET_OFFSET_NAME),
            }
            tasks.append(task)

        self._task_list = tasks

    # c4d.gui.GeDialog

    def CreateLayout(self):
        r""" This is called when the dialog should create its initial
        interface. We create the basic layout and load the tasks that
        have been stored in the active document. """

        self._last_doc = None
        self.SetTitle('Task List')

        # Layout flag that will cause the widget to be scaled as much
        # possible in horizontal and vertical direction.
        BF_FULLFIT = c4d.BFH_SCALEFIT | c4d.BFV_SCALEFIT

        # Create the main group that will encapsulate all of the
        # dialogs widgets. We can pass 0 if we don't want to supply
        # a specific ID.
        self.GroupBegin(0, BF_FULLFIT, cols=1, rows=0)
        self.GroupBorderSpace(4, 4, 4, 4)

        # This widget displays the active document's title.
        self.AddStaticText(res.TEXT_DOCINFO, c4d.BFH_CENTER)

        # Create a new Scroll Group that will contain the widgets
        # for each task. Since a Scroll Group can't have specific
        # number of columns and rows, we'll have to place an inner
        # group.
        # We will also give the Scroll Group a status bar where we
        # place the "+" button in and give it some border and spacing.
        scrollflags = c4d.SCROLLGROUP_VERT | c4d.SCROLLGROUP_AUTOVERT | \
                      c4d.SCROLLGROUP_STATUSBAR_EXT_GROUP | c4d.SCROLLGROUP_STATUSBAR
        self.ScrollGroupBegin(0, BF_FULLFIT, scrollflags=scrollflags)
        self.GroupBorderNoTitle(c4d.BORDER_ROUND)
        self.GroupBorderSpace(4, 4, 4, 2)
        self.GroupBegin(res.GROUP_TASKS, c4d.BFH_SCALEFIT | c4d.BFV_TOP,
                cols=res.TASKWIDGET_REALCOUNT, rows=0)

        # Call the procedure that will insert the widgets for each
        # task into the dialog. We don't need it to flush the group
        # though because it does not contain any items yet.
        self.Refresh(initial=True)

        self.GroupEnd() # GROUP_TASKS
        self.GroupEnd() # Wrapper Scroll Group

        # Create the Button to add new Tasks in the status
        # bar group of the Scroll Group.
        self.LayoutFlushGroup(c4d.ID_SCROLLGROUP_STATUSBAR_EXTLEFT_GROUP)
        self.AddButton(res.BUTTON_NEWTASK, c4d.BFH_RIGHT, name="+")
        self.LayoutChanged(c4d.ID_SCROLLGROUP_STATUSBAR_EXTLEFT_GROUP)
        return True

    def CoreMessage(self, kind, bc):
        r""" Responds to what's happening inside of Cinema 4D. In this
        case, we're looking to see if the active document has changed. """

        # One case this message is being sent is when the active
        # document has changed.
        if kind in [c4d.EVMSG_CHANGE, c4d.EVMSG_DOCUMENTRECALCULATED]:
            update = (kind == c4d.EVMSG_CHANGE)
            self.Refresh(force=update, reload_=update)

        return True

    def Command(self, param, bc):
        r""" This is called when the user clicks a button or types into
        a text field. We use this to update the task list and save the
        changed data into the document. """

        # Add a new task if the user pressed the button for it.
        if param == res.BUTTON_NEWTASK:
            self._task_list.append(
                    {'done': False, 'name': self.DEFAULT_TASK_NAME}
            )
            self.SaveTasks()
            self.Refresh(force=True)

            # Compute the ID of the newly created text field of
            # the task.
            widget_id = self.ComputeTaskId(
                    len(self._task_list) - 1, res.TASKWIDGET_OFFSET_NAME)

            # Set the focus to the newly created Task and emulate
            # a CTRL+A input event so that all the contents in the
            # edit field are selected.
            self.Activate(widget_id)

            msg = c4d.BaseContainer(c4d.BFM_INPUT)
            msg.SetLong(c4d.BFM_INPUT_DEVICE, c4d.BFM_INPUT_KEYBOARD)
            msg.SetString(c4d.BFM_INPUT_ASC, '')
            msg.SetLong(c4d.BFM_INPUT_CHANNEL, ord('A'))
            msg.SetLong(c4d.BFM_INPUT_QUALIFIER, c4d.QCTRL)
            self.SendMessage(widget_id, msg)

        # Or check if the user triggered one of the dynamic widgets.
        elif param >= res.DYNAMIC_TASKS_START:

            # Calculate the index of the task and the offset ID
            # of the widget that was triggered.
            delta = param - res.DYNAMIC_TASKS_START
            (task_index, widget_offset) = divmod(delta, res.TASKWIDGET_COUNT)

            # Will be set when the triggered widget was handled.
            # We will later save and/or refresh based on these
            # values.
            changed = False
            refresh = False

            # Update the value of the adressed task depending on
            # which widget was triggered.
            if task_index < len(self._task_list):
                task = self._task_list[task_index]

                if widget_offset == res.TASKWIDGET_OFFSET_STATE:
                    task['done'] = self.GetBool(param)
                    changed = True

                    # Enable or disable the text widget for
                    # this entry based on the state.
                    text_id = self.ComputeTaskId(
                            task_index, res.TASKWIDGET_OFFSET_NAME)
                    self.Enable(text_id, not task['done'])

                elif widget_offset == res.TASKWIDGET_OFFSET_NAME:

                    # Check the message container if the String
                    # has changed. If it did not, this event tells
                    # us that the user finished editing the field.
                    if not bc.GetLong(c4d.BFM_ACTION_STRCHG):
                        changed = True

                    # Otherwise, we'll update the internal Task List.
                    else:
                        task['name'] = self.GetString(param)

                elif widget_offset == res.TASKWIDGET_OFFSET_REMOVE:
                    del self._task_list[task_index]
                    changed = True
                    refresh = True

            if changed:
                self.SaveTasks()
            if refresh:
                self.Refresh(force=True)

        return True

class Command(c4d.plugins.CommandData):
    r""" Implements the behavior of the Plugin Command and is being
    registered to the application with :meth:`Register`. When invoked,
    it opens the :class:`TaskListDialog` asynchronously. """

    def Register(self):
        return c4d.plugins.RegisterCommandPlugin(
                PLUGIN_ID, "Task List", 0, None, "", self)

    @property
    def dialog(self):
        if not hasattr(self, '_dialog'):
            self._dialog = TaskListDialog()
        return self._dialog

    # c4d.plugins.CommandData

    def Execute(self, doc):
        return self.dialog.Open(c4d.DLG_TYPE_ASYNC, PLUGIN_ID)

    def RestoreLayout(self, secret):
        return self.dialog.Restore(PLUGIN_ID, secret)

if __name__ == '__main__':
    Command().Register()

