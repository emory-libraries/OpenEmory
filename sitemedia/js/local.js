/* make console.log not an error even if console is not available */
if (!window.console) console = {};
console.log = console.log || function(){};
console.warn = console.warn || function(){};
console.error = console.error || function(){};
console.info = console.info || function(){};


String.prototype.ucfirst = function() {
    // method to uppercase the first letter in a string
    return this.substr(0, 1).toUpperCase() + this.substr(1);
}

/* Function to prevent the enter key from submitting a form.
   On a keypress event it disables the default action so the
   form is not submitted. Enter acts normally while inside a
   textarea element. 

 param id - id of form

*/
function disableEnter(id){
    $(id).keypress(function(event) {
        // 13 is the key code for the <ENTER> key
        if(event.which == 13 && event.target.type!="textarea"){  
            event.preventDefault();
        }
    });

} 
