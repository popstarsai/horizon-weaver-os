# bootc update review

Updates replace the OS image. Avoid suggesting runtime package changes to /usr.
Separate booted, staged and rollback deployments. A rollback switches the image;
it does not restore /var, agent memory or user data. Preserve upstream bootguard
and do not replace its boot-success logic with model decisions. Local bootc status
does not establish remote update availability or hardware compatibility.
