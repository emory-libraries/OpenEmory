/**

jQuery plugin for ajax-editable tags.

Example usage:
  <script type="text/javascript" charset="utf-8">
    $(document).ready(function () {
      $(".tag-edit").editableTags();
    });
  </script>

Where the corresponding html looks something like this:

  <div class="tag-edit">
    <p class="tag-list">
       <span class="tags">tag, tag, tag... </span>
       <a class="edit">edit</a>
    </p>
    <form action="/tags" style="display:none">
      <input type="text" name="tags" value="tag, tag, tag..."/>
      <input type="submit"/>
      <input type="button" name="cancel" value="Cancel"/>
    </form
  <div>


Initialization options:

  message_class: CSS class to use for success/error messages (default: message)

  form: jQuery selector for the tag edit form (default: form)

  tag_container: jQuery selector for element that contains the tags
      and edit link or button (i.e., anything that should be hidden
      when in edit mode) (default: .tag-list)

  tags: jQuery selector for element that contains just the tags,
      for updating on successful form submission (default: .tags)

  edit: jQuery selector for element to trigger edit mode 
      (default: .edit)

  cancel: jQuery selector for element to exit edit mode without saving
      (default: input[name=cancel])

  input_tags: jQuery selector for form element that will contain the
      tags to be sent on form submission (default: input[name=tags])

Behavior details:

On form submission, will perform an Ajax PUT to the URL set in the
form's action attribute with the data in the tag input form element.

*/        

(function( $ ){
  var plugin_name = 'editableTags';
  // utility methods used for multi-term autocomplete
  function split(val) {
      return val.split( /,\s*/ );
  }
  function extractLast(term) {
      return split(term).pop();
  }

  var methods = {
      init : function(options) { 
          if (options == null) {
              options = {};
          }
          // default settings
          var settings = {
              'message_class': 'message',
              'form': 'form',
              'tag_container': '.tag-list',
              'tags': '.tags',
              'edit': '.edit',
              'cancel': 'input[name=cancel]',
              'input_tags': 'input[name=tags]',
          };

        return this.each(function(){
            var $this = $(this);

            if (options) {
                $.extend(settings, options);
            }
            // find needed elements relative to plugin element
            $.each(['form','tag_container','tags','edit','cancel', 'input_tags'],
                   function(){
                settings[this] = $this.find(settings[this]);
            });
            // bind edit link to switch into editing mode
            settings.edit.click(methods.start_editing);
            // bind cancel button to switch out of editing mode
            settings.cancel.click(methods.end_editing);
            // bind form submit method
            settings.form.submit(methods.submit);
            // store settings data with plugin name
            // - saving in multiple places for access on sub-element events
            $.each([$this, settings.edit, settings.form, settings.cancel], function() {
                this.data(plugin_name, settings);
            });

            // autocomplete url is configured: set up multi-term autocomplete 
            if (settings.autocomplete) {
                settings.form.find('input[type=text]')
                    // don't navigate away from the field on tab when selecting an item
  		    .bind("keydown", function( event ) {
			if (event.keyCode === $.ui.keyCode.TAB &&
			     $(this).data("autocomplete").menu.active ) {
			    event.preventDefault();
			}
		    })
                    // configure autocomplete behavior
                    .autocomplete({
                    source: function(request, response){
                        $.getJSON(settings.autocomplete, 
                                  {s: extractLast(request.term)}, response);
                    },
                    search: function(){
                        var term = extractLast(this.value);
                        if (term.length < 2) { return false; }
                    },
                    focus: function() {	// prevent value inserted on focus
                        return false;
                    },
                    select: function(event, ui) {
                        var terms = split(this.value);
                        // remove current input
                        terms.pop();
                        // add selected item
                        terms.push(ui.item.value);
                        // add placeholder to get the comma-and-space at the end
			terms.push("");
			this.value = terms.join(", ");
			return false;
                    }
                });
                
            }
        });
      },

      // switch into editing mode: display the form, hide the tag display container
      start_editing: function(event) {
          if (event) { event.preventDefault(); }
          // set focus on the first text input (i.e., tag field)
          $(this).data(plugin_name).form.show().find('input[type=text]').focus();
          $(this).data(plugin_name).tag_container.hide();
      },
      // switch out of editing mode: hide the form, show the tag display container
      end_editing: function(event){
          if (event) { event.preventDefault(); }
          $(this).data(plugin_name).form.hide();
          $(this).data(plugin_name).tag_container.show();
      },

      // utility method to show a message that will fade out
      // params: parent (element to append to), text of the message, 
      // and a css class to add to the message element (e.g., success or error)
      show_message: function(parent, text, cls){
          var msgcls = $(this).data(plugin_name).message_class;
          parent.find('.' + msgcls).remove();
          $('<span/>').addClass(msgcls).html(text).addClass(cls).appendTo(parent)
              .delay(1000).fadeOut(1500);
      },

      // update the displayed tags; takes a list of tags OR an object
      // with tag values and urls
      update_tags: function(tags) {
          if (tags.type == 'list') {
              // simple list return
              $(this).data(plugin_name).tags.html(tags.join(', '));
          } else {
              // return is an object with tags and corresponding URLs
              // clear out previous content
              $(this).data(plugin_name).tags.html('');
              // create link elements and add to the tags element
              for (var tag in tags) {
                  var link = $('<a/>').attr('href', tags[tag]).html(tag);
                  $(this).data(plugin_name).tags.append(link)
              }
              // add dividing text after every link but the last one
              $(this).data(plugin_name).tags.find('a').not(':last').after(', ');
          }
      },

      // tag edit form submit behavior: PUT tag data to the form action url
      submit: function(event) {
        event.preventDefault();
        var tagform = $(this).data(plugin_name).form;
        $.ajax({
            type: 'PUT',
            data: tagform.data(plugin_name).input_tags.val(),
            url: tagform.attr('action'),
            accepts: 'application/json',
            // pass Django CSRF token (may not actually be necessary for PUT)
            headers: {'X-CSRFTOKEN': tagform.find('input[name=csrfmiddlewaretoken]').val()},
            success: function(data, status, xhr) {
                // update displayed tags with the version returned (possibly normalized)
                methods.update_tags.apply(tagform, [data]);
                // finish editing - hide form, display message
                methods.end_editing.apply(tagform);
                methods.show_message.apply(tagform, [tagform.data(plugin_name).tag_container,
                                     'Saved', 'success']);
            },
            error: function(xhr, status, error) {
                msg = status.ucfirst();
                if (xhr.getResponseHeader('Content-Type') == 'text/plain') {
                    msg += ': ' + xhr.responseText
                }
                methods.show_message.apply(tagform, [tagform, msg, 'error']);
            }
        });
      }

  };

  $.fn.editableTags = function( method ) {
    // Method calling logic
    if ( methods[method] ) {
      return methods[ method ].apply( this, Array.prototype.slice.call( arguments, 1 ));
    } else if ( typeof method === 'object' || ! method ) {
      return methods.init.apply( this, arguments );
    } else {
      $.error( 'Method ' +  method + ' does not exist on jQuery.editableTags' );
    }    
  
  };

})( jQuery );

